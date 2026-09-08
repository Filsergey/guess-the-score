from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

import app.oracle as oracle
from app.providers.sstats import SStatsProvider

_LIMIT = 5
_FETCH_LIMIT = 20
_CACHE_TTL_SECONDS = 30 * 60
_CACHE: dict[tuple[int, str], tuple[float, list[dict]]] = {}
_CACHE_LOCK = asyncio.Lock()
_ORIGINAL_MATCH_CONTEXT = None
_INSTALLED = False


def _rows(payload) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data") or payload.get("response") or []
    if isinstance(data, dict):
        return [data]
    return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []


def _value(row: dict, *names):
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return None


def _date(value) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif value not in (None, ""):
        text = str(value).strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _score(row: dict, home: bool):
    if home:
        return _value(row, "scoreHomeFT", "ScoreHomeFT", "scoreHome", "ScoreHome", "homeResult", "HomeResult")
    return _value(row, "scoreAwayFT", "ScoreAwayFT", "scoreAway", "ScoreAway", "awayResult", "AwayResult")


def _int_score(value) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _is_unfinished(row: dict) -> bool:
    status = str(_value(row, "status", "Status", "statusShort", "StatusShort") or "").strip().upper()
    if not status:
        return False
    live_or_future = {
        "NS", "TBD", "SCHEDULED", "UPCOMING", "LIVE", "1H", "2H", "HT", "ET", "BT", "P", "INT", "POSTPONED", "CANCELLED",
    }
    return status in live_or_future or status.startswith("LIVE")


def _normalize_rows(payload, team_provider_id: int, before: datetime) -> list[dict]:
    provider = SStatsProvider()
    result = []
    for raw in _rows(payload):
        row = provider._normalize_game(raw)
        played_at = _date(_value(row, "date", "Date", "kickoffAt", "KickoffAt"))
        if played_at is None or played_at >= before or _is_unfinished(row):
            continue
        home_score = _int_score(_score(row, True))
        away_score = _int_score(_score(row, False))
        if home_score is None or away_score is None:
            continue
        home_id = _value(row, "homeTeamId", "HomeTeamId")
        away_id = _value(row, "awayTeamId", "AwayTeamId")
        try:
            home_id_i = int(home_id) if home_id is not None else None
            away_id_i = int(away_id) if away_id is not None else None
        except (TypeError, ValueError):
            home_id_i = away_id_i = None
        if team_provider_id not in {home_id_i, away_id_i}:
            continue
        home_name = str(_value(row, "homeTeamName", "HomeTeamName") or "Хозяева")
        away_name = str(_value(row, "awayTeamName", "AwayTeamName") or "Гости")
        competition = str(_value(row, "leagueName", "LeagueName", "competitionName", "CompetitionName") or "")
        own = home_score if home_id_i == team_provider_id else away_score
        opp = away_score if home_id_i == team_provider_id else home_score
        result.append({
            "date": played_at.date().isoformat(),
            "home": home_name,
            "away": away_name,
            "score": f"{home_score}:{away_score}",
            "competition": competition,
            "result": "W" if own > opp else ("D" if own == opp else "L"),
            "_sort": played_at.timestamp(),
        })
    result.sort(key=lambda item: item["_sort"], reverse=True)
    for item in result:
        item.pop("_sort", None)
    return result[:_LIMIT]


async def _fetch_recent(team_provider_id: int, before: datetime) -> list[dict]:
    provider = SStatsProvider()
    params = {
        "Team": int(team_provider_id),
        "Ended": True,
        "Limit": _FETCH_LIMIT,
        "Offset": 0,
        "Order": "Date DESC",
        "TimeZone": 0,
    }
    try:
        payload = await provider._get("Games/list", params, timeout=3.2)
        rows = _normalize_rows(payload, team_provider_id, before)
        if rows:
            return rows
    except Exception:
        pass

    # Main-API fallback. Games/query is already used elsewhere in the app and
    # lets us recover recent fixtures even when the simple Team filter is absent
    # for a particular SStats response shape.
    try:
        payload = await provider._post(
            "Games/query",
            {
                "Condition": f"HomeTeamId = {int(team_provider_id)} OR AwayTeamId = {int(team_provider_id)}",
                "Fields": [
                    "Id", "Date", "Status", "LeagueName",
                    "HomeTeamId", "HomeTeamName", "AwayTeamId", "AwayTeamName",
                    "ScoreHome", "ScoreAway", "ScoreHomeFT", "ScoreAwayFT",
                ],
                "Format": "json",
                "Timezone": 0,
                "Order": "Date DESC",
                "Limit": _FETCH_LIMIT,
            },
            timeout=3.2,
        )
        return _normalize_rows(payload, team_provider_id, before)
    except Exception:
        return []


async def _cached_recent(team_provider_id: int, before: datetime) -> list[dict]:
    key = (int(team_provider_id), before.date().isoformat())
    now = time.monotonic()
    stale = None
    async with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached:
            expires_at, rows = cached
            stale = rows
            if expires_at > now:
                return [dict(row) for row in rows]

    rows = await _fetch_recent(team_provider_id, before)
    if rows:
        async with _CACHE_LOCK:
            _CACHE[key] = (now + _CACHE_TTL_SECONDS, [dict(row) for row in rows])
        return rows
    # A temporary SStats failure should not make a previously complete list
    # disappear and accidentally trigger an Oracle DELTA.
    return [dict(row) for row in stale] if stale else []


async def _recent_match_context(match, db):
    ctx = await _ORIGINAL_MATCH_CONTEXT(match, db)
    if getattr(match, "provider", None) != "sstats":
        return ctx

    home = ctx.get("home")
    away = ctx.get("away")
    tasks = []
    sides = []
    for side, team in (("home", home), ("away", away)):
        provider_id = getattr(team, "provider_id", None)
        if provider_id is None:
            continue
        sides.append(side)
        tasks.append(asyncio.create_task(_cached_recent(int(provider_id), match.kickoff_at)))
    if not tasks:
        return ctx

    fetched = await asyncio.gather(*tasks, return_exceptions=True)
    recent = {key: list(value) for key, value in (ctx.get("recent_matches") or {}).items()}
    changed = False
    for side, value in zip(sides, fetched):
        if isinstance(value, Exception) or not value:
            continue
        recent[side] = value[:_LIMIT]
        changed = True
    if not changed:
        return ctx

    # These concrete rows are both shown to the user and supplied to OpenAI.
    # Aggregated last_10 remains the primary form signal; the rows provide
    # readable opponent/score context.
    ctx["recent_matches"] = recent
    snapshot = dict(ctx.get("snapshot") or {})
    snapshot["recent_matches"] = recent
    ctx["snapshot"] = snapshot
    ctx["context_hash"] = oracle._canonical_hash(snapshot)
    return ctx


def install_oracle_recent_matches() -> None:
    global _INSTALLED, _ORIGINAL_MATCH_CONTEXT
    if _INSTALLED:
        return
    _INSTALLED = True
    _ORIGINAL_MATCH_CONTEXT = oracle._match_context
    oracle._match_context = _recent_match_context
