from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

import app.oracle as oracle
from app.providers.sstats import SStatsProvider

_MAX_MATCHES = 5
_MAX_INFLUENCE_PCT = 10.0
_PROVIDER_CACHE_TTL_SECONDS = 6 * 60 * 60
_PROVIDER_CACHE: dict[tuple[int, int], tuple[float, list[dict]]] = {}
_PROVIDER_CACHE_LOCK = asyncio.Lock()
_ORIGINAL_MATCH_CONTEXT = None
_ORIGINAL_COMPOSE_PAYLOAD = None
_INSTALLED = False


def _parse_score(value) -> tuple[int, int] | None:
    try:
        left, right = str(value or "").split(":", 1)
        return int(left), int(right)
    except (TypeError, ValueError):
        return None


def _parse_date(value) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _value(row: dict, *names):
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return None


def _int_value(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _rows(payload) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data") or payload.get("response") or []
    if isinstance(data, dict):
        return [data]
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def _normalize_provider_h2h(
    payload,
    home_provider_id: int,
    away_provider_id: int,
    home_name: str,
    away_name: str,
    before: datetime,
) -> list[dict]:
    provider = SStatsProvider()
    before_utc = before if before.tzinfo else before.replace(tzinfo=timezone.utc)
    before_utc = before_utc.astimezone(timezone.utc)
    result = []

    for raw in _rows(payload):
        row = provider._normalize_game(raw)
        home_id = _int_value(_value(row, "homeTeamId", "HomeTeamId"))
        away_id = _int_value(_value(row, "awayTeamId", "AwayTeamId"))
        if {home_id, away_id} != {int(home_provider_id), int(away_provider_id)}:
            continue

        played_at = _parse_date(_value(row, "date", "Date", "kickoffAt", "KickoffAt"))
        if played_at is None or played_at >= before_utc:
            continue

        home_score = _int_value(
            _value(
                row,
                "scoreHomeFT",
                "ScoreHomeFT",
                "scoreHome",
                "ScoreHome",
                "homeFTResult",
                "HomeFTResult",
                "homeResult",
                "HomeResult",
            )
        )
        away_score = _int_value(
            _value(
                row,
                "scoreAwayFT",
                "ScoreAwayFT",
                "scoreAway",
                "ScoreAway",
                "awayFTResult",
                "AwayFTResult",
                "awayResult",
                "AwayResult",
            )
        )
        if home_score is None or away_score is None:
            continue

        if home_id == int(home_provider_id):
            row_home_name, row_away_name = home_name, away_name
        else:
            row_home_name, row_away_name = away_name, home_name

        result.append(
            {
                "date": played_at.date().isoformat(),
                "home": row_home_name,
                "away": row_away_name,
                "score": f"{home_score}:{away_score}",
                "competition": str(
                    _value(row, "leagueName", "LeagueName", "competitionName", "CompetitionName") or ""
                ),
                "_sort": played_at.timestamp(),
            }
        )

    result.sort(key=lambda item: item["_sort"], reverse=True)
    for item in result:
        item.pop("_sort", None)
    return result[:_MAX_MATCHES]


async def _query_provider_h2h(
    home_provider_id: int,
    away_provider_id: int,
    home_name: str,
    away_name: str,
    before: datetime,
) -> list[dict]:
    provider = SStatsProvider()
    fields = [
        "Id",
        "Date",
        "Status",
        "LeagueId",
        "LeagueName",
        "HomeTeamId",
        "HomeTeamName",
        "AwayTeamId",
        "AwayTeamName",
        "ScoreHome",
        "ScoreAway",
        "ScoreHomeFT",
        "ScoreAwayFT",
    ]
    body = {
        "Condition": (
            f"(HomeTeamId = {int(home_provider_id)} AND AwayTeamId = {int(away_provider_id)}) "
            f"OR (HomeTeamId = {int(away_provider_id)} AND AwayTeamId = {int(home_provider_id)})"
        ),
        "Fields": fields,
        "Format": "json",
        "Timezone": 0,
        "Order": "Date DESC",
        "Limit": 20,
    }
    try:
        payload = await provider._post("Games/query", body, timeout=3.2)
        rows = _normalize_provider_h2h(
            payload, home_provider_id, away_provider_id, home_name, away_name, before
        )
        if rows:
            return rows
    except Exception:
        pass

    # Fallback to two exact conditions if the provider's query parser does not
    # accept grouped OR expressions.
    async def one(host_id: int, guest_id: int):
        try:
            return await provider._post(
                "Games/query",
                {
                    "Condition": f"HomeTeamId = {int(host_id)} AND AwayTeamId = {int(guest_id)}",
                    "Fields": fields,
                    "Format": "json",
                    "Timezone": 0,
                    "Order": "Date DESC",
                    "Limit": 10,
                },
                timeout=3.2,
            )
        except Exception:
            return {"data": []}

    first, second = await asyncio.gather(
        one(home_provider_id, away_provider_id),
        one(away_provider_id, home_provider_id),
    )
    merged_payload = {"data": _rows(first) + _rows(second)}
    return _normalize_provider_h2h(
        merged_payload, home_provider_id, away_provider_id, home_name, away_name, before
    )


async def _cached_provider_h2h(
    home_provider_id: int,
    away_provider_id: int,
    home_name: str,
    away_name: str,
    before: datetime,
) -> list[dict]:
    key = tuple(sorted((int(home_provider_id), int(away_provider_id))))
    now = time.monotonic()
    async with _PROVIDER_CACHE_LOCK:
        cached = _PROVIDER_CACHE.get(key)
        if cached and cached[0] > now:
            return [dict(row) for row in cached[1]]

    rows = await _query_provider_h2h(
        home_provider_id, away_provider_id, home_name, away_name, before
    )
    async with _PROVIDER_CACHE_LOCK:
        _PROVIDER_CACHE[key] = (
            now + _PROVIDER_CACHE_TTL_SECONDS,
            [dict(row) for row in rows],
        )
    return rows


def _merge_rows(local_rows: list[dict], provider_rows: list[dict]) -> list[dict]:
    merged = []
    seen = set()
    for row in list(provider_rows) + list(local_rows):
        key = (
            str(row.get("date") or ""),
            str(row.get("home") or "").casefold(),
            str(row.get("away") or "").casefold(),
            str(row.get("score") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(dict(row))

    merged.sort(
        key=lambda row: _parse_date(row.get("date")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return merged[:_MAX_MATCHES]


def _recency_weight(age_days: int) -> float:
    years = max(0.0, float(age_days) / 365.25)
    if years <= 1:
        return 1.0
    if years <= 2:
        return 0.80
    if years <= 3:
        return 0.60
    if years <= 5:
        return 0.35
    if years <= 10:
        return 0.10
    return 0.02


def _empty_metrics() -> dict:
    return {
        "count": 0,
        "home_wins": 0,
        "draws": 0,
        "away_wins": 0,
        "home_goals": 0,
        "away_goals": 0,
        "avg_total_goals": None,
        "btts_rate": None,
        "over_2_5_rate": None,
        "sample_factor": 0.0,
        "recency_factor": 0.0,
        "relevance": 0.0,
        "relevance_pct": 0.0,
        "max_influence_pct": _MAX_INFLUENCE_PCT,
        "effective_influence_pct": 0.0,
        "latest_age_days": None,
        "oldest_age_days": None,
        "quality": "none",
    }


def _h2h_metrics(rows: list[dict], home_name: str, away_name: str, before: datetime) -> dict:
    if not rows:
        return _empty_metrics()

    before_utc = before
    if before_utc.tzinfo is None:
        before_utc = before_utc.replace(tzinfo=timezone.utc)
    before_utc = before_utc.astimezone(timezone.utc)

    home_wins = draws = away_wins = 0
    home_goals = away_goals = 0
    btts = overs = 0
    age_days_list: list[int] = []
    recency_weights: list[float] = []
    valid = 0

    for row in rows[:_MAX_MATCHES]:
        score = _parse_score(row.get("score"))
        played_at = _parse_date(row.get("date"))
        if score is None or played_at is None:
            continue

        raw_home_goals, raw_away_goals = score
        row_home = str(row.get("home") or "").casefold()
        row_away = str(row.get("away") or "").casefold()
        wanted_home = str(home_name or "").casefold()
        wanted_away = str(away_name or "").casefold()

        if row_home == wanted_home and row_away == wanted_away:
            own, opp = raw_home_goals, raw_away_goals
        elif row_home == wanted_away and row_away == wanted_home:
            own, opp = raw_away_goals, raw_home_goals
        else:
            if row_home == wanted_home:
                own, opp = raw_home_goals, raw_away_goals
            elif row_away == wanted_home:
                own, opp = raw_away_goals, raw_home_goals
            else:
                continue

        age_days = max(0, (before_utc.date() - played_at.date()).days)
        age_days_list.append(age_days)
        recency_weights.append(_recency_weight(age_days))
        valid += 1
        home_goals += own
        away_goals += opp
        btts += int(own > 0 and opp > 0)
        overs += int(own + opp >= 3)
        if own > opp:
            home_wins += 1
        elif own < opp:
            away_wins += 1
        else:
            draws += 1

    if not valid:
        return _empty_metrics()

    sample_factor = min(1.0, valid / float(_MAX_MATCHES))
    recency_factor = sum(recency_weights) / valid
    relevance = max(0.0, min(1.0, sample_factor * recency_factor))
    effective = _MAX_INFLUENCE_PCT * relevance
    if relevance >= 0.60 and valid >= 4:
        quality = "high"
    elif relevance >= 0.25 and valid >= 2:
        quality = "medium"
    else:
        quality = "low"

    return {
        "count": valid,
        "home_wins": home_wins,
        "draws": draws,
        "away_wins": away_wins,
        "home_goals": home_goals,
        "away_goals": away_goals,
        "avg_total_goals": round((home_goals + away_goals) / valid, 2),
        "btts_rate": round(btts / valid, 2),
        "over_2_5_rate": round(overs / valid, 2),
        "sample_factor": round(sample_factor, 3),
        "recency_factor": round(recency_factor, 3),
        "relevance": round(relevance, 3),
        "relevance_pct": round(relevance * 100, 1),
        "max_influence_pct": _MAX_INFLUENCE_PCT,
        "effective_influence_pct": round(effective, 2),
        "latest_age_days": min(age_days_list),
        "oldest_age_days": max(age_days_list),
        "quality": quality,
    }


def _summary(metrics: dict) -> str:
    if not metrics or not metrics.get("count"):
        return "Завершённые очные встречи до этого матча не найдены."
    return (
        f"Последние {metrics['count']} очных встреч: "
        f"{metrics['home_wins']} побед хозяев, {metrics['draws']} ничьих, "
        f"{metrics['away_wins']} побед гостей; голы {metrics['home_goals']}:{metrics['away_goals']}. "
        f"Актуальность H2H {metrics['relevance_pct']}%, поэтому его допустимое влияние "
        f"на прогноз ограничено {metrics['effective_influence_pct']}%."
    )


async def _match_context_with_weighted_h2h(match, db):
    ctx = await _ORIGINAL_MATCH_CONTEXT(match, db)
    local_rows = list(ctx.get("head_to_head_matches") or [])
    home = ctx.get("home")
    away = ctx.get("away")
    rows = local_rows

    if getattr(match, "provider", None) == "sstats" and len(local_rows) < _MAX_MATCHES:
        home_provider_id = getattr(home, "provider_id", None)
        away_provider_id = getattr(away, "provider_id", None)
        if home_provider_id is not None and away_provider_id is not None:
            provider_rows = await _cached_provider_h2h(
                int(home_provider_id),
                int(away_provider_id),
                getattr(home, "name", "Хозяева"),
                getattr(away, "name", "Гости"),
                match.kickoff_at,
            )
            rows = _merge_rows(local_rows, provider_rows)

    ctx["head_to_head_matches"] = rows
    metrics = _h2h_metrics(
        rows,
        getattr(home, "name", "Хозяева"),
        getattr(away, "name", "Гости"),
        match.kickoff_at,
    )
    ctx["head_to_head_metrics"] = metrics

    # Keep full H2H rows for the UI, but do not send them to OpenAI. The model
    # receives only compact server-computed metrics, which is cheaper and prevents
    # ancient H2H from being overinterpreted.
    snapshot = dict(ctx.get("snapshot") or {})
    if rows:
        snapshot.pop("head_to_head_matches", None)
        snapshot["head_to_head"] = metrics
    # With no H2H rows keep the original empty-list snapshot unchanged. This
    # avoids a one-time DELTA/OpenAI refresh merely because the representation
    # changed, while an empty list costs essentially nothing in future prompts.
    ctx["snapshot"] = snapshot
    ctx["context_hash"] = oracle._canonical_hash(snapshot)
    return ctx


def _compose_payload_with_weighted_h2h(ctx, ai, mode):
    payload = _ORIGINAL_COMPOSE_PAYLOAD(ctx, ai, mode)
    metrics = dict(ctx.get("head_to_head_metrics") or _empty_metrics())
    payload["head_to_head_metrics"] = metrics
    payload["head_to_head"] = _summary(metrics)
    payload["head_to_head_matches"] = list(ctx.get("head_to_head_matches") or [])
    return payload


def install_oracle_h2h() -> None:
    global _INSTALLED, _ORIGINAL_MATCH_CONTEXT, _ORIGINAL_COMPOSE_PAYLOAD
    if _INSTALLED:
        return
    _INSTALLED = True
    _ORIGINAL_MATCH_CONTEXT = oracle._match_context
    _ORIGINAL_COMPOSE_PAYLOAD = oracle._compose_payload
    oracle._match_context = _match_context_with_weighted_h2h
    oracle._compose_payload = _compose_payload_with_weighted_h2h
    oracle.ANALYSIS_INSTRUCTIONS += """

Правило H2H: поле context.head_to_head уже агрегировано сервером. Считай H2H только вспомогательным фактором. Поле effective_influence_pct — верхняя граница его влияния на итоговый прогноз; не превышай её. relevance_pct отражает актуальность с учётом давности и количества встреч. Если relevance_pct близко к нулю, считай H2H практически нейтральным и не используй старые матчи как аргумент для сильного изменения счёта или вероятностей."""
