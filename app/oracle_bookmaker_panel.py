from __future__ import annotations

import copy
import statistics
from collections import defaultdict

import app.oracle as oracle
import app.oracle_enrichment as enrichment

# Stable, quality-first bookmaker panel. Names are matched after the same
# normalization oracle_enrichment already uses for SStats labels.
# We keep more than seven candidates here because availability differs by match,
# but only the first seven available books are used for the market aggregate.
_TOP_BOOKMAKERS = [
    ("Pinnacle", ("pinnacle", "pinnacle sports")),
    ("Betfair", ("betfair", "betfair exchange")),
    ("bet365", ("bet365", "bet 365")),
    ("Unibet", ("unibet",)),
    ("William Hill", ("william hill", "williamhill")),
    ("Betway", ("betway",)),
    ("Bwin", ("bwin",)),
    ("Betano", ("betano",)),
    ("10Bet", ("10bet", "10 bet")),
    ("Marathonbet", ("marathonbet", "marathon bet")),
    ("1xBet", ("1xbet", "1x bet")),
]

_MIN_PREFERRED = 3
_MAX_PANEL = 7
_MARKET_ODDS_RELATIVE_DELTA = 0.03  # ignore market noise below 3%
_MARKET_PROBABILITY_POINTS_DELTA = 2.0
_INSTALLED = False
_ORIGINAL_BOOKMAKER_MARKET = None
_ORIGINAL_MATCH_CONTEXT = None
_ORIGINAL_REFRESH = None


def _bookmaker_label(row: dict, index: int) -> str:
    for key in ("bookmakerName", "BookmakerName", "name", "Name"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    value = row.get("bookmakerId", row.get("BookmakerId", index))
    return str(value)


def _preferred_rank(label: str) -> tuple[int, str] | None:
    normalized = enrichment._norm(label)
    compact = normalized.replace(" ", "")
    for index, (canonical, aliases) in enumerate(_TOP_BOOKMAKERS):
        for alias in aliases:
            candidate = enrichment._norm(alias)
            if (
                normalized == candidate
                or compact == candidate.replace(" ", "")
                or candidate in normalized
            ):
                return index, canonical
    return None


def _parse_bookmaker(row: dict, index: int) -> dict | None:
    label = _bookmaker_label(row, index)
    rank = _preferred_rank(label)
    raw_values: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    bets = row.get("odds") or []
    if not isinstance(bets, list):
        return None

    for bet in bets:
        if not isinstance(bet, dict):
            continue
        market = enrichment._market_key(bet.get("marketName"))
        if not market:
            continue
        prices = bet.get("odds") or []
        if not isinstance(prices, list):
            continue
        for price in prices:
            if not isinstance(price, dict):
                continue
            outcome = enrichment._canonical_outcome(market, price.get("name"))
            try:
                number = float(price.get("value"))
            except (TypeError, ValueError):
                continue
            if not outcome or number <= 1.0 or number > 1000:
                continue
            raw_values[market][outcome].append(number)

    if not raw_values:
        return None

    values: dict[str, dict[str, float]] = {}
    for market, outcomes in raw_values.items():
        market_row = {}
        for outcome, quotes in outcomes.items():
            if quotes:
                market_row[outcome] = float(statistics.median(quotes))
        if market_row:
            values[market] = market_row
    if not values:
        return None

    return {
        "label": label,
        "normalized": enrichment._norm(label),
        "preferred_rank": rank[0] if rank else None,
        "canonical": rank[1] if rank else label,
        "values": values,
    }


def _select_panel(parsed: list[dict]) -> tuple[list[dict], bool]:
    preferred = sorted(
        (row for row in parsed if row["preferred_rank"] is not None),
        key=lambda row: (row["preferred_rank"], row["normalized"]),
    )

    # Deduplicate aliases/duplicate feeds of the same preferred bookmaker.
    preferred_unique = []
    seen_rank = set()
    for row in preferred:
        rank = row["preferred_rank"]
        if rank in seen_rank:
            continue
        seen_rank.add(rank)
        preferred_unique.append(row)

    if len(preferred_unique) >= _MIN_PREFERRED:
        return preferred_unique[:_MAX_PANEL], False

    # If SStats does not expose at least three panel books for this match, retain
    # available preferred books and fill the remaining slots deterministically.
    # This is intentionally capped at seven instead of averaging every feed.
    selected = list(preferred_unique)
    selected_names = {row["normalized"] for row in selected}
    fallback = sorted(
        (row for row in parsed if row["normalized"] not in selected_names),
        key=lambda row: row["normalized"],
    )
    for row in fallback:
        if len(selected) >= _MAX_PANEL:
            break
        selected.append(row)
    return selected, True


def _aggregate_panel(payload) -> dict:
    rows = enrichment._payload_rows(payload)
    parsed = [item for i, row in enumerate(rows) if (item := _parse_bookmaker(row, i))]
    if not parsed:
        return {"bookmaker_count": 0, "aggregation": "median", "panel": "top_bookmakers"}

    selected, fallback_used = _select_panel(parsed)
    values: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for bookmaker in selected:
        for market, outcomes in bookmaker["values"].items():
            for outcome, value in outcomes.items():
                values[market][outcome].append(float(value))

    result: dict[str, object] = {
        "panel": "top_bookmakers",
        "aggregation": "median",
        "fallback_used": fallback_used,
        "bookmaker_count": len(selected),
        "bookmakers_used": [row["canonical"] for row in selected],
    }
    order = {
        "match_winner": ("home", "draw", "away"),
        "home_away": ("home", "away"),
        "goals_over_under": ("over_1_5", "under_1_5", "over_2_5", "under_2_5"),
        "btts": ("yes", "no"),
    }
    for market, outcomes in order.items():
        market_row = {}
        for outcome in outcomes:
            quotes = values[market].get(outcome) or []
            if not quotes:
                continue
            median_odds = float(statistics.median(quotes))
            # Two decimals intentionally suppress meaningless feed jitter such as
            # 1.089 -> 1.091 while keeping real market moves visible.
            odds = round(median_odds, 2)
            market_row[outcome] = {
                # Keep the legacy field name consumed by the current prompt/UI;
                # its aggregation is now explicitly identified as median above.
                "avg_odds": odds,
                "implied_pct": round(100.0 / odds, 1),
            }
        if market_row:
            result[market] = market_row
    return result


async def _panel_bookmaker_market(match) -> tuple[dict, str | None]:
    if getattr(match, "provider", None) != "sstats":
        return {"bookmaker_count": 0, "aggregation": "median", "panel": "top_bookmakers"}, None
    try:
        payload = await enrichment.SStatsProvider()._get(f"Odds/{int(match.provider_id)}", timeout=3.2)
        return _aggregate_panel(payload), None
    except Exception as exc:
        return {"bookmaker_count": 0, "aggregation": "median", "panel": "top_bookmakers"}, f"odds:{type(exc).__name__}"


def _strip_market_metadata(value):
    snapshot = copy.deepcopy(value)
    market = snapshot.get("bookmaker_market") if isinstance(snapshot, dict) else None
    if isinstance(market, dict):
        for key in ("bookmaker_count", "bookmakers_used", "fallback_used", "panel", "aggregation"):
            market.pop(key, None)
        for market_row in market.values():
            if not isinstance(market_row, dict):
                continue
            for outcome_row in market_row.values():
                if isinstance(outcome_row, dict):
                    outcome_row.pop("quotes", None)
    return snapshot


def _relative_change(before: float, after: float) -> float:
    base = max(abs(before), 1e-9)
    return abs(after - before) / base


def _ignored_metadata_path(path: tuple[str, ...]) -> bool:
    return bool(
        path
        and path[0] == "bookmaker_market"
        and path[-1] in {"bookmaker_count", "bookmakers_used", "fallback_used", "panel", "aggregation", "quotes"}
    )


def _is_market_odds_path(path: tuple[str, ...]) -> bool:
    return bool(path and ((path[0] == "bookmaker_market" and path[-1] == "avg_odds") or path[:2] == ("signals", "odds")))


def _is_market_probability_path(path: tuple[str, ...]) -> bool:
    return bool(path and path[0] == "bookmaker_market" and path[-1] == "implied_pct")


def _meaningful_diff(old, new, path: tuple[str, ...] = ()):
    if old == new or _ignored_metadata_path(path):
        return None

    if isinstance(old, dict) and isinstance(new, dict):
        result = {}
        for key in sorted(set(old) | set(new)):
            child_path = path + (str(key),)
            if _ignored_metadata_path(child_path):
                continue
            if key not in old:
                result[key] = {"after": new[key]}
                continue
            if key not in new:
                # Temporary disappearance of an odds feed/market must not spend
                # tokens. A newly appearing market can still be considered later.
                if child_path and child_path[0] == "bookmaker_market":
                    continue
                result[key] = {"removed": True}
                continue
            child = _meaningful_diff(old[key], new[key], child_path)
            if child is not None:
                result[key] = child
        return result or None

    if isinstance(old, list) and isinstance(new, list):
        return {"after": new}

    try:
        before_num = float(old)
        after_num = float(new)
    except (TypeError, ValueError):
        before_num = after_num = None

    if before_num is not None and after_num is not None:
        if _is_market_odds_path(path) and _relative_change(before_num, after_num) < _MARKET_ODDS_RELATIVE_DELTA:
            return None
        if _is_market_probability_path(path) and abs(after_num - before_num) < _MARKET_PROBABILITY_POINTS_DELTA:
            return None

    return {"before": old, "after": new}


async def _stable_match_context(match, db):
    ctx = await _ORIGINAL_MATCH_CONTEXT(match, db)
    market = ctx.get("bookmaker_market") or {}
    winner = market.get("match_winner") if isinstance(market, dict) else None

    # Use the same stable top-bookmaker median as the generic 1X2 signal. This
    # avoids having a second, unknown SStats Winner1/X/2 feed trigger DELTA noise.
    if isinstance(winner, dict) and all(isinstance(winner.get(key), dict) for key in ("home", "draw", "away")):
        panel_odds = {
            key: winner[key].get("avg_odds")
            for key in ("home", "draw", "away")
            if winner[key].get("avg_odds") is not None
        }
        if len(panel_odds) == 3:
            signals = copy.deepcopy(ctx.get("signals") or {})
            signals["odds"] = panel_odds
            ctx["signals"] = signals
            snapshot = copy.deepcopy(ctx["snapshot"])
            snapshot.setdefault("signals", {})["odds"] = panel_odds
            ctx["snapshot"] = snapshot

    # Bookmaker availability/names are useful display/debug metadata, but they do
    # not define whether OpenAI should be called. Hash only the analytical values.
    ctx["context_hash"] = oracle._canonical_hash(_strip_market_metadata(ctx["snapshot"]))
    return ctx


async def _stable_refresh(db, match, force=False):
    item = await _ORIGINAL_REFRESH(db, match, force=force)
    if force or item.get("status") != "needs-ai" or item.get("mode") != "delta":
        return item

    previous = item.get("previous") or {}
    ctx = item.get("ctx") or {}
    changes = _meaningful_diff(previous.get("context_snapshot") or {}, ctx.get("snapshot") or {}) or {}
    if not changes:
        return {
            "match_id": match.id,
            "status": "cache-unchanged",
            "ai": False,
            "previous": previous,
            "ctx": ctx,
        }
    item["changes"] = changes
    return item


def install_bookmaker_panel() -> None:
    global _INSTALLED, _ORIGINAL_BOOKMAKER_MARKET, _ORIGINAL_MATCH_CONTEXT, _ORIGINAL_REFRESH
    if _INSTALLED:
        return
    _INSTALLED = True

    _ORIGINAL_BOOKMAKER_MARKET = enrichment._bookmaker_market
    enrichment._bookmaker_market = _panel_bookmaker_market

    _ORIGINAL_MATCH_CONTEXT = oracle._match_context
    oracle._match_context = _stable_match_context

    _ORIGINAL_REFRESH = oracle._refresh_one_context
    oracle._refresh_one_context = _stable_refresh

    note = (
        "\nВ bookmaker_market используется стабильная панель приоритетных букмекеров "
        "(до 7 источников) и медиана котировок. Поле avg_odds сохранено для совместимости, "
        "но его значение является медианой выбранной панели. Если доступно меньше 3 "
        "приоритетных букмекеров, панель дополняется стабильным fallback до 7 источников."
    )
    if "стабильная панель приоритетных букмекеров" not in oracle.ANALYSIS_INSTRUCTIONS:
        oracle.ANALYSIS_INSTRUCTIONS = oracle.ANALYSIS_INSTRUCTIONS.rstrip() + note
