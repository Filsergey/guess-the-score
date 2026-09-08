from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher

import app.oracle as oracle
import app.oracle_h2h as weighted_h2h
from app.providers.sstats import SStatsProvider

logger = logging.getLogger(__name__)

_MAX_MATCHES = 5
_TEAM_ID_CACHE_TTL = 24 * 60 * 60
_H2H_CACHE_TTL = 6 * 60 * 60
_NEGATIVE_CACHE_TTL = 10 * 60
_TEAM_ID_CACHE: dict[tuple[int, str], tuple[float, str | None]] = {}
_H2H_CACHE: dict[tuple[str, str], tuple[float, list[dict]]] = {}
_CACHE_LOCK = asyncio.Lock()
_ORIGINAL_MATCH_CONTEXT = None
_INSTALLED = False


def _rows(payload) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data", payload.get("response", payload))
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        for key in ("items", "matches", "events", "games", "rows", "list"):
            value = data.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        return [data]
    return []


def _norm(value) -> str:
    text = str(value or "").casefold()
    text = re.sub(r"\b(fc|cf|fk|sc|afc|club|football|futbol)\b", " ", text)
    return re.sub(r"[^a-z0-9а-яё]+", "", text)


def _name_similarity(left, right) -> float:
    a, b = _norm(left), _norm(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.94
    return SequenceMatcher(None, a, b).ratio()


def _clean_ls_id(value) -> str | None:
    if value in (None, "") or isinstance(value, (dict, list)):
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.split("?", 1)[0].rstrip("/")
    if "/" in text:
        parts = [part for part in text.split("/") if part]
        if parts:
            text = parts[-1]
    text = text.strip()
    return text or None


def _preferred_ls_id(row: dict, provider: SStatsProvider) -> str | None:
    preferred = (
        "flashId",
        "FlashId",
        "flashscoreId",
        "FlashscoreId",
        "lsId",
        "LsId",
        "teamFlashId",
        "TeamFlashId",
        "teamId",
        "TeamId",
        "id",
        "Id",
        "uid",
        "Uid",
        "url",
        "Url",
        "link",
        "Link",
    )
    non_numeric = []
    numeric = []
    for name in preferred:
        value = provider._deep_value(row, name)
        candidate = _clean_ls_id(value)
        if not candidate:
            continue
        if any(ch.isalpha() for ch in candidate):
            non_numeric.append(candidate)
        else:
            numeric.append(candidate)
    return (non_numeric or numeric or [None])[0]


def _parse_date(value) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        number = float(value)
        if number > 10_000_000_000:
            number /= 1000.0
        try:
            dt = datetime.fromtimestamp(number, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    elif value not in (None, ""):
        text = str(value).strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            dt = None
            for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S"):
                try:
                    dt = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            if dt is None:
                return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _int_score(value) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


async def _resolve_ls_team_id(provider_id: int, team_name: str) -> str | None:
    cache_key = (int(provider_id), _norm(team_name))
    now = time.monotonic()
    async with _CACHE_LOCK:
        cached = _TEAM_ID_CACHE.get(cache_key)
        if cached and cached[0] > now:
            return cached[1]

    provider = SStatsProvider()
    resolved = None

    # Main SStats teams are mapped to Flashscore. Prefer the direct mapping when
    # the team endpoint exposes it, because it avoids any fuzzy name matching.
    try:
        payload = await provider.get_team(int(provider_id))
        obj = provider._payload_object(payload)
        for key in ("flashId", "FlashId", "flashscoreId", "FlashscoreId", "lsId", "LsId"):
            resolved = _clean_ls_id(provider._deep_value(obj, key))
            if resolved:
                break
    except Exception:
        pass

    # Fallback documented by SStats: /Ls/Teams supports team search. Pick the
    # closest name, but prefer Flashscore-looking (non-numeric) identifiers.
    if not resolved:
        try:
            payload = await provider._get(
                "Ls/Teams",
                {"name": team_name, "Limit": 20, "Offset": 0},
                timeout=3.5,
            )
            candidates = []
            for row in _rows(payload):
                candidate_name = provider._deep_value(
                    row,
                    "teamName",
                    "TeamName",
                    "name",
                    "Name",
                    "title",
                    "Title",
                )
                candidate_id = _preferred_ls_id(row, provider)
                if not candidate_id:
                    continue
                similarity = _name_similarity(candidate_name, team_name)
                alpha_bonus = 0.05 if any(ch.isalpha() for ch in candidate_id) else 0.0
                candidates.append((similarity + alpha_bonus, candidate_id))
            if candidates:
                candidates.sort(reverse=True)
                if candidates[0][0] >= 0.65:
                    resolved = candidates[0][1]
        except Exception:
            pass

    ttl = _TEAM_ID_CACHE_TTL if resolved else _NEGATIVE_CACHE_TTL
    async with _CACHE_LOCK:
        _TEAM_ID_CACHE[cache_key] = (now + ttl, resolved)
    return resolved


def _row_side_id(row: dict, provider: SStatsProvider, side: str) -> str | None:
    normalized = provider._normalize_game(row)
    if side == "home":
        raw = normalized.get("homeTeamId", normalized.get("HomeTeamId"))
        nested = provider._deep_value(row.get("homeTeam", row.get("HomeTeam", {})), "id", "Id", "flashId", "FlashId")
    else:
        raw = normalized.get("awayTeamId", normalized.get("AwayTeamId"))
        nested = provider._deep_value(row.get("awayTeam", row.get("AwayTeam", {})), "id", "Id", "flashId", "FlashId")
    return _clean_ls_id(raw) or _clean_ls_id(nested)


def _normalize_ls_h2h(
    payload,
    home_ls_id: str,
    away_ls_id: str,
    home_name: str,
    away_name: str,
    before: datetime,
) -> list[dict]:
    provider = SStatsProvider()
    before_utc = before if before.tzinfo else before.replace(tzinfo=timezone.utc)
    before_utc = before_utc.astimezone(timezone.utc)
    wanted_home_id = _clean_ls_id(home_ls_id)
    wanted_away_id = _clean_ls_id(away_ls_id)
    result = []

    for raw in _rows(payload):
        row = provider._normalize_game(raw)
        played_at = _parse_date(
            row.get("date")
            or row.get("Date")
            or provider._deep_value(raw, "startTime", "StartTime", "kickoffAt", "KickoffAt", "timestamp", "Timestamp")
        )
        if played_at is None or played_at >= before_utc:
            continue

        home_score = _int_score(
            row.get("scoreHomeFT")
            or row.get("ScoreHomeFT")
            or row.get("scoreHome")
            or row.get("ScoreHome")
            or row.get("homeFTResult")
            or row.get("HomeFTResult")
            or row.get("homeResult")
            or row.get("HomeResult")
            or provider._deep_value(raw, "homeScore", "HomeScore")
        )
        away_score = _int_score(
            row.get("scoreAwayFT")
            or row.get("ScoreAwayFT")
            or row.get("scoreAway")
            or row.get("ScoreAway")
            or row.get("awayFTResult")
            or row.get("AwayFTResult")
            or row.get("awayResult")
            or row.get("AwayResult")
            or provider._deep_value(raw, "awayScore", "AwayScore")
        )
        if home_score is None or away_score is None:
            continue

        raw_home_name = str(
            row.get("homeTeamName")
            or row.get("HomeTeamName")
            or provider._deep_value(raw.get("homeTeam", raw.get("HomeTeam", {})), "name", "Name")
            or ""
        )
        raw_away_name = str(
            row.get("awayTeamName")
            or row.get("AwayTeamName")
            or provider._deep_value(raw.get("awayTeam", raw.get("AwayTeam", {})), "name", "Name")
            or ""
        )
        row_home_id = _row_side_id(raw, provider, "home")
        row_away_id = _row_side_id(raw, provider, "away")

        if row_home_id and wanted_home_id and row_home_id == wanted_home_id:
            display_home, display_away = home_name, away_name
        elif row_home_id and wanted_away_id and row_home_id == wanted_away_id:
            display_home, display_away = away_name, home_name
        else:
            direct = _name_similarity(raw_home_name, home_name) + _name_similarity(raw_away_name, away_name)
            reverse = _name_similarity(raw_home_name, away_name) + _name_similarity(raw_away_name, home_name)
            if reverse > direct:
                display_home, display_away = away_name, home_name
            else:
                display_home, display_away = home_name, away_name

        competition = str(
            row.get("leagueName")
            or row.get("LeagueName")
            or provider._deep_value(raw, "leagueName", "LeagueName", "competitionName", "CompetitionName")
            or ""
        )
        result.append(
            {
                "date": played_at.date().isoformat(),
                "home": display_home,
                "away": display_away,
                "score": f"{home_score}:{away_score}",
                "competition": competition,
                "source": "SStats / Flashscore",
                "_sort": played_at.timestamp(),
            }
        )

    result.sort(key=lambda item: item["_sort"], reverse=True)
    for item in result:
        item.pop("_sort", None)
    return result[:_MAX_MATCHES]


async def _fetch_flashscore_h2h(
    home_provider_id: int,
    away_provider_id: int,
    home_name: str,
    away_name: str,
    before: datetime,
) -> list[dict]:
    home_ls_id, away_ls_id = await asyncio.gather(
        _resolve_ls_team_id(home_provider_id, home_name),
        _resolve_ls_team_id(away_provider_id, away_name),
    )
    if not home_ls_id or not away_ls_id:
        logger.info(
            "Oracle H2H Flashscore team mapping missing: home=%s/%s away=%s/%s",
            home_name,
            home_ls_id,
            away_name,
            away_ls_id,
        )
        return []

    cache_key = tuple(sorted((home_ls_id, away_ls_id)))
    now = time.monotonic()
    async with _CACHE_LOCK:
        cached = _H2H_CACHE.get(cache_key)
        if cached and cached[0] > now:
            return [dict(row) for row in cached[1]]

    provider = SStatsProvider()
    rows = []
    params = {
        "BothTeams": f"{home_ls_id},{away_ls_id}",
        "Ended": True,
        "Limit": 30,
        "Offset": 0,
        "TimeZone": 0,
    }
    try:
        payload = await provider._get("Ls/List", params, timeout=4.5)
        rows = _normalize_ls_h2h(payload, home_ls_id, away_ls_id, home_name, away_name, before)
    except Exception as exc:
        logger.info("Oracle H2H Flashscore query failed: %s", type(exc).__name__)

    # Some deployments of the LS endpoint are stricter about accepted filters;
    # retry the documented minimum request before giving up.
    if not rows:
        try:
            payload = await provider._get(
                "Ls/List",
                {"BothTeams": f"{home_ls_id},{away_ls_id}", "Limit": 30, "TimeZone": 0},
                timeout=4.5,
            )
            rows = _normalize_ls_h2h(payload, home_ls_id, away_ls_id, home_name, away_name, before)
        except Exception as exc:
            logger.info("Oracle H2H Flashscore minimal query failed: %s", type(exc).__name__)

    ttl = _H2H_CACHE_TTL if rows else _NEGATIVE_CACHE_TTL
    async with _CACHE_LOCK:
        _H2H_CACHE[cache_key] = (now + ttl, [dict(row) for row in rows])
    logger.info(
        "Oracle H2H Flashscore: %s - %s ids=%s,%s rows=%s",
        home_name,
        away_name,
        home_ls_id,
        away_ls_id,
        len(rows),
    )
    return rows


async def _match_context_with_flashscore_h2h(match, db):
    ctx = await _ORIGINAL_MATCH_CONTEXT(match, db)
    current_rows = list(ctx.get("head_to_head_matches") or [])
    if len(current_rows) >= _MAX_MATCHES or getattr(match, "provider", None) != "sstats":
        return ctx

    home = ctx.get("home")
    away = ctx.get("away")
    home_provider_id = getattr(home, "provider_id", None)
    away_provider_id = getattr(away, "provider_id", None)
    if home_provider_id is None or away_provider_id is None:
        return ctx

    flash_rows = await _fetch_flashscore_h2h(
        int(home_provider_id),
        int(away_provider_id),
        getattr(home, "name", "Хозяева"),
        getattr(away, "name", "Гости"),
        match.kickoff_at,
    )
    rows = weighted_h2h._merge_rows(current_rows, flash_rows)
    if not rows:
        ctx["head_to_head_source"] = "none"
        return ctx

    ctx["head_to_head_matches"] = rows
    metrics = weighted_h2h._h2h_metrics(
        rows,
        getattr(home, "name", "Хозяева"),
        getattr(away, "name", "Гости"),
        match.kickoff_at,
    )
    ctx["head_to_head_metrics"] = metrics
    ctx["head_to_head_source"] = "sstats-flashscore"

    snapshot = dict(ctx.get("snapshot") or {})
    snapshot.pop("head_to_head_matches", None)
    snapshot["head_to_head"] = metrics
    ctx["snapshot"] = snapshot
    ctx["context_hash"] = oracle._canonical_hash(snapshot)
    return ctx


def install_oracle_h2h_flashscore() -> None:
    global _INSTALLED, _ORIGINAL_MATCH_CONTEXT
    if _INSTALLED:
        return
    _INSTALLED = True
    _ORIGINAL_MATCH_CONTEXT = oracle._match_context
    oracle._match_context = _match_context_with_flashscore_h2h
