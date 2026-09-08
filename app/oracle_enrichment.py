from __future__ import annotations

import asyncio
import re
import unicodedata
from collections import defaultdict

import app.oracle as oracle
from app.providers.sstats import SStatsProvider

# Five-season UEFA sporting club coefficients established for 2026/27.
# They are fixed for seeding during this season, so keeping the relevant UCL
# clubs locally avoids another network request every time a prediction is opened.
# Format: aliases -> (UEFA rank, coefficient points).
_UEFA_2026_ROWS = [
    (1, 147.500, ("bayern munchen", "bayern munich", "fc bayern munchen", "bayern")),
    (2, 144.500, ("real madrid",)),
    (3, 132.000, ("paris", "paris saint germain", "psg")),
    (4, 130.000, ("liverpool",)),
    (5, 127.000, ("inter", "internazionale", "inter milan")),
    (6, 125.500, ("manchester city", "man city")),
    (7, 119.000, ("arsenal",)),
    (8, 113.250, ("barcelona", "fc barcelona")),
    (9, 105.000, ("bayer leverkusen", "leverkusen")),
    (10, 104.750, ("atletico madrid", "atletico de madrid", "atleti")),
    (11, 100.750, ("borussia dortmund", "dortmund")),
    (12, 99.250, ("chelsea",)),
    (13, 97.750, ("roma", "as roma")),
    (14, 90.000, ("benfica", "sl benfica")),
    (15, 84.000, ("sporting", "sporting cp", "sporting lisbon")),
    (16, 84.000, ("atalanta",)),
    (17, 83.000, ("aston villa",)),
    (18, 83.000, ("eintracht frankfurt", "eintracht")),
    (19, 82.000, ("tottenham", "tottenham hotspur", "spurs")),
    (20, 80.750, ("porto", "fc porto")),
    (21, 76.500, ("manchester united", "man united")),
    (22, 76.250, ("fiorentina",)),
    (23, 75.250, ("club brugge", "club brugge kv")),
    (24, 74.500, ("real betis", "real betis balompie")),
    (25, 72.250, ("juventus",)),
    (26, 71.250, ("psv", "psv eindhoven")),
    (27, 71.000, ("feyenoord", "feyenoord rotterdam")),
    (28, 69.000, ("west ham", "west ham united")),
    (29, 68.750, ("lille", "lille osc")),
    (30, 66.000, ("ac milan", "milan")),
    (31, 65.750, ("olympique lyon", "lyon")),
    (32, 64.000, ("bodo glimt", "bodo/glimt", "bodø/glimt")),
    (33, 63.750, ("braga", "sporting braga")),
    (34, 63.000, ("napoli",)),
    (35, 62.875, ("az alkmaar", "az")),
    (36, 62.250, ("olympiacos", "olympiakos", "olympiakos piraeus")),
    (37, 61.000, ("rb leipzig", "leipzig")),
    (39, 59.000, ("villarreal",)),
    (45, 56.250, ("shakhtar donetsk", "shakhtar")),
    (49, 53.500, ("galatasaray",)),
    (59, 44.000, ("slavia prague", "slavia praha")),
    (80, 27.500, ("vfb stuttgart", "stuttgart")),
    (103, 19.989, ("como", "como 1907")),
    (120, 16.699, ("lens", "rc lens")),
]


def _norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    text = text.casefold().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


_UEFA_2026 = {
    _norm(alias): {"rank": rank, "coefficient": coefficient, "season": "2026/27"}
    for rank, coefficient, aliases in _UEFA_2026_ROWS
    for alias in aliases
}


def _uefa_coefficient(team) -> dict | None:
    if team is None:
        return None
    for candidate in (getattr(team, "name", None), getattr(team, "source_name", None), getattr(team, "code", None)):
        key = _norm(candidate)
        if key in _UEFA_2026:
            return dict(_UEFA_2026[key])
    return None


def _payload_rows(payload) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get("data") or payload.get("response") or []
    if isinstance(rows, dict):
        rows = [rows]
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _price_key(value: object) -> str:
    return _norm(value).replace(" ", "_")


def _market_key(value: object) -> str | None:
    name = _norm(value)
    if not name:
        return None
    if "both teams" in name or "btts" in name or "both team" in name or "obe komandy" in name:
        return "btts"
    if "home away" in name or name in {"homeaway", "draw no bet"}:
        return "home_away"
    if "match winner" in name or "1x2" in name or "full time result" in name or name == "winner":
        return "match_winner"
    if "over under" in name or "total goals" in name or "goals over" in name or name == "total":
        return "goals_over_under"
    return None


def _canonical_outcome(market: str, value: object) -> str | None:
    name = _norm(value)
    compact = name.replace(" ", "")
    if market == "match_winner":
        if name in {"home", "1", "home win"}: return "home"
        if name in {"draw", "x"}: return "draw"
        if name in {"away", "2", "away win"}: return "away"
    if market == "home_away":
        if name in {"home", "1", "home win"}: return "home"
        if name in {"away", "2", "away win"}: return "away"
    if market == "btts":
        if name in {"yes", "both teams to score yes", "btts yes"}: return "yes"
        if name in {"no", "both teams to score no", "btts no"}: return "no"
    if market == "goals_over_under":
        match = re.search(r"(over|under)\s*([0-9]+(?:[\.,][0-9]+)?)", name)
        if not match:
            match = re.search(r"([0-9]+(?:[\.,][0-9]+)?)\s*(over|under)", name)
            if match:
                side, line = match.group(2), match.group(1)
            else:
                return None
        else:
            side, line = match.group(1), match.group(2)
        line = line.replace(",", ".")
        if line not in {"1.5", "2.5"}:
            return None
        return f"{side}_{line.replace('.', '_')}"
    return None


def _average_market(payload) -> dict:
    rows = _payload_rows(payload)
    values: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    usable_bookmakers = set()
    for idx, bookmaker in enumerate(rows):
        bookmaker_id = bookmaker.get("bookmakerId", bookmaker.get("bookmakerName", idx))
        found = False
        bets = bookmaker.get("odds") or []
        if not isinstance(bets, list):
            continue
        for bet in bets:
            if not isinstance(bet, dict):
                continue
            market = _market_key(bet.get("marketName"))
            if not market:
                continue
            prices = bet.get("odds") or []
            if not isinstance(prices, list):
                continue
            for price in prices:
                if not isinstance(price, dict):
                    continue
                outcome = _canonical_outcome(market, price.get("name"))
                try:
                    number = float(price.get("value"))
                except (TypeError, ValueError):
                    continue
                if not outcome or number <= 1.0 or number > 1000:
                    continue
                values[market][outcome].append(number)
                found = True
        if found:
            usable_bookmakers.add(str(bookmaker_id))

    result: dict[str, object] = {"bookmaker_count": len(usable_bookmakers)}
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
            avg = sum(quotes) / len(quotes)
            market_row[outcome] = {
                "avg_odds": round(avg, 3),
                "implied_pct": round(100.0 / avg, 1),
                "quotes": len(quotes),
            }
        if market_row:
            result[market] = market_row
    return result


async def _bookmaker_market(match) -> tuple[dict, str | None]:
    if getattr(match, "provider", None) != "sstats":
        return {"bookmaker_count": 0}, None
    try:
        payload = await SStatsProvider()._get(f"Odds/{int(match.provider_id)}", timeout=3.2)
        return _average_market(payload), None
    except Exception as exc:
        return {"bookmaker_count": 0}, f"odds:{type(exc).__name__}"


def _deep_number(obj, aliases: tuple[str, ...]):
    wanted = {_norm(x).replace(" ", "") for x in aliases}
    if isinstance(obj, dict):
        for key, value in obj.items():
            nk = _norm(key).replace(" ", "")
            if nk in wanted and not isinstance(value, (dict, list)):
                try:
                    return float(value)
                except (TypeError, ValueError):
                    pass
        for value in obj.values():
            found = _deep_number(value, aliases)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _deep_number(value, aliases)
            if found is not None:
                return found
    return None


def _last10_side(raw) -> dict:
    games = _deep_number(raw, ("gamesCount", "games", "count", "matches"))
    wins = _deep_number(raw, ("wins", "winCount", "won"))
    draws = _deep_number(raw, ("draws", "drawCount"))
    losses = _deep_number(raw, ("losses", "loss", "lossCount", "lost"))
    avg_for = _deep_number(raw, ("goalsFor", "avgGoalsFor", "goalsScored", "avgGoalsScored", "scoredGoals", "goals"))
    avg_against = _deep_number(raw, ("goalsAgainst", "avgGoalsAgainst", "goalsConceded", "avgGoalsConceded", "concededGoals"))
    games_i = int(games) if games is not None else 10
    result = {
        "games": games_i,
        "wins": int(wins) if wins is not None else None,
        "draws": int(draws) if draws is not None else None,
        "losses": int(losses) if losses is not None else None,
        "avg_goals_for": round(avg_for, 3) if avg_for is not None else None,
        "avg_goals_against": round(avg_against, 3) if avg_against is not None else None,
    }
    if avg_for is not None and games_i > 0:
        result["goals_for"] = int(round(avg_for * games_i))
    if avg_against is not None and games_i > 0:
        result["goals_against"] = int(round(avg_against * games_i))
    return {key: value for key, value in result.items() if value is not None}


async def _last10_from_sstats(match) -> tuple[dict | None, str | None]:
    if getattr(match, "provider", None) != "sstats":
        return None, None
    try:
        payload = await SStatsProvider()._get(
            "Games/last-games-stats",
            {
                "gameId": int(match.provider_id),
                "limit": 10,
                "sameLeague": "false",
                "sameSeason": "false",
                "homeAway": "false",
            },
            timeout=3.2,
        )
        data = payload.get("data") or payload.get("response") or payload
        if not isinstance(data, dict):
            return None, None
        home = data.get("home") or data.get("Home")
        away = data.get("away") or data.get("Away")
        if not isinstance(home, dict) or not isinstance(away, dict):
            return None, None
        return {"home": _last10_side(home), "away": _last10_side(away)}, None
    except Exception as exc:
        return None, f"last10:{type(exc).__name__}"


async def _last10_from_db(team_id, before, db) -> dict:
    rows = await oracle._recent_models(team_id, before, db, limit=10)
    wins = draws = losses = gf = ga = 0
    for row in rows:
        own, opp = (
            (row.home_goals, row.away_goals)
            if row.home_team_id == team_id
            else (row.away_goals, row.home_goals)
        )
        gf += int(own or 0)
        ga += int(opp or 0)
        if own > opp: wins += 1
        elif own == opp: draws += 1
        else: losses += 1
    return {"games": len(rows), "wins": wins, "draws": draws, "losses": losses, "goals_for": gf, "goals_against": ga}


_ORIGINAL_MATCH_CONTEXT = None
_INSTALLED = False


async def _enriched_match_context(match, db):
    # SStats network enrichments can run while the existing context is collected.
    odds_task = asyncio.create_task(_bookmaker_market(match))
    last10_task = asyncio.create_task(_last10_from_sstats(match))
    ctx = await _ORIGINAL_MATCH_CONTEXT(match, db)
    bookmaker_market, odds_error = await odds_task
    last10, last10_error = await last10_task

    # SStats last-games-stats covers all competitions. DB is only a fallback.
    if not last10:
        last10 = {
            "home": await _last10_from_db(match.home_team_id, match.kickoff_at, db),
            "away": await _last10_from_db(match.away_team_id, match.kickoff_at, db),
        }

    uefa = {
        "home": _uefa_coefficient(ctx.get("home")),
        "away": _uefa_coefficient(ctx.get("away")),
    }
    uefa = {key: value for key, value in uefa.items() if value is not None}

    snapshot = dict(ctx["snapshot"])
    snapshot["last_10"] = last10
    if uefa:
        snapshot["uefa_club_coefficient"] = uefa
    if int(bookmaker_market.get("bookmaker_count") or 0) > 0:
        snapshot["bookmaker_market"] = bookmaker_market

    errors = list(ctx.get("errors") or [])
    errors.extend(x for x in (odds_error, last10_error) if x)
    ctx.update({
        "last_10": last10,
        "uefa_club_coefficient": uefa,
        "bookmaker_market": bookmaker_market,
        "errors": errors,
        "snapshot": snapshot,
        "context_hash": oracle._canonical_hash(snapshot),
    })
    return ctx


_EXTRA_INSTRUCTIONS = """
Дополнительные сигналы context:
- uefa_club_coefficient — пятилетний UEFA club coefficient: rank и coefficient. Это долгосрочный показатель силы клуба в еврокубках; учитывай его, но не ставь выше свежей формы и рынка.
- last_10 — последние 10 завершённых матчей команды во всех доступных турнирах: wins/draws/losses, goals_for/goals_against и, когда доступны, средние голы.
- bookmaker_market — агрегированная доматчевая линия нескольких букмекеров. bookmaker_count — число букмекеров с полезными котировками. Для 1X2, Home/Away, тоталов 1.5/2.5 и BTTS передаются avg_odds и implied_pct.
implied_pct считается как 100 / avg_odds и СОДЕРЖИТ букмекерскую маржу, поэтому проценты разных исходов не обязаны суммироваться до 100. Не считай коррелирующие рынки независимыми доказательствами. Используй 1X2 как сильный сигнал исхода, Over/Under — как сигнал ожидаемой результативности, BTTS — как сигнал вероятности голов обеих команд.
"""


def install_oracle_enrichment() -> None:
    global _INSTALLED, _ORIGINAL_MATCH_CONTEXT
    if _INSTALLED:
        return
    _INSTALLED = True
    _ORIGINAL_MATCH_CONTEXT = oracle._match_context
    oracle._match_context = _enriched_match_context
    if "bookmaker_market" not in oracle.ANALYSIS_INSTRUCTIONS:
        oracle.ANALYSIS_INSTRUCTIONS = oracle.ANALYSIS_INSTRUCTIONS.rstrip() + "\n" + _EXTRA_INSTRUCTIONS.strip()
