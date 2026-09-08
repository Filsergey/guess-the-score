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
_GAME_ID_CACHE_TTL = 24 * 60 * 60
_H2H_CACHE_TTL = 6 * 60 * 60
_NEGATIVE_CACHE_TTL = 2 * 60
_TEAM_ID_CACHE: dict[tuple[int, str], tuple[float, str | None]] = {}
_GAME_ID_CACHE: dict[int, tuple[float, tuple[str | None, str | None]]] = {}
_H2H_CACHE: dict[tuple[str, str], tuple[float, list[dict]]] = {}
_CACHE_LOCK = asyncio.Lock()
_ORIGINAL_MATCH_CONTEXT = None
_INSTALLED = False


def _rows(payload) -> list[dict]:
    """Extract a list from the slightly different SStats/LS response shapes."""
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []

    for key in ("data", "Data", "response", "Response", "items", "Items", "matches", "Matches", "events", "Events", "games", "Games", "rows", "Rows", "list", "List"):
        value = payload.get(key)
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
        if isinstance(value, dict):
            nested = _rows(value)
            if nested:
                return nested
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
    return text.strip() or None


def _looks_flash_id(value) -> bool:
    text = _clean_ls_id(value)
    return bool(text and len(text) >= 5 and any(ch.isalpha() for ch in text))


def _dict_value(obj: dict, *names):
    if not isinstance(obj, dict):
        return None
    wanted = {str(name).casefold() for name in names}
    for key, value in obj.items():
        if str(key).casefold() in wanted and value not in (None, ""):
            return value
    return None


def _preferred_ls_id(obj, provider: SStatsProvider) -> str | None:
    if not isinstance(obj, dict):
        candidate = _clean_ls_id(obj)
        return candidate if _looks_flash_id(candidate) else None
    for name in (
        "flashId", "FlashId", "flashscoreId", "FlashscoreId", "lsId", "LsId",
        "teamFlashId", "TeamFlashId", "teamId", "TeamId", "id", "Id", "uid", "Uid",
        "url", "Url", "link", "Link",
    ):
        candidate = _clean_ls_id(provider._deep_value(obj, name))
        if _looks_flash_id(candidate):
            return candidate
    return None


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
            for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
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
    if isinstance(value, dict):
        for name in ("current", "Current", "display", "Display", "normalTime", "Normaltime", "value", "Value"):
            if name in value:
                parsed = _int_score(value[name])
                if parsed is not None:
                    return parsed
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _find_side_block(obj, side: str):
    if not isinstance(obj, dict):
        return None
    names = (
        ("homeTeam", "HomeTeam", "homeParticipant", "HomeParticipant", "home", "Home", "team1", "Team1", "participant1", "Participant1")
        if side == "home"
        else ("awayTeam", "AwayTeam", "awayParticipant", "AwayParticipant", "away", "Away", "team2", "Team2", "participant2", "Participant2")
    )
    value = _dict_value(obj, *names)
    if isinstance(value, (dict, str)):
        return value
    for child in obj.values():
        if isinstance(child, dict):
            found = _find_side_block(child, side)
            if found is not None:
                return found
    return None


def _collect_named_entities(obj, provider: SStatsProvider, out: list[tuple[str, str]]):
    if isinstance(obj, dict):
        name = _dict_value(obj, "name", "Name", "teamName", "TeamName", "title", "Title")
        candidate = _preferred_ls_id(obj, provider)
        if name and candidate:
            out.append((str(name), candidate))
        for value in obj.values():
            _collect_named_entities(value, provider, out)
    elif isinstance(obj, list):
        for value in obj:
            _collect_named_entities(value, provider, out)


def _side_id_from_info(obj: dict, side: str, team_name: str, provider: SStatsProvider) -> str | None:
    direct_names = (
        ("homeFlashId", "HomeFlashId", "homeTeamFlashId", "HomeTeamFlashId", "homeTeamId", "HomeTeamId")
        if side == "home"
        else ("awayFlashId", "AwayFlashId", "awayTeamFlashId", "AwayTeamFlashId", "awayTeamId", "AwayTeamId")
    )
    direct = _clean_ls_id(provider._deep_value(obj, *direct_names))
    if _looks_flash_id(direct):
        return direct

    block = _find_side_block(obj, side)
    candidate = _preferred_ls_id(block, provider)
    if candidate:
        return candidate

    entities: list[tuple[str, str]] = []
    _collect_named_entities(obj, provider, entities)
    if entities:
        scored = sorted(((_name_similarity(name, team_name), ident) for name, ident in entities), reverse=True)
        if scored[0][0] >= 0.72:
            return scored[0][1]
    return None


async def _resolve_ls_ids_from_current_game(game_id: int, home_name: str, away_name: str) -> tuple[str | None, str | None]:
    now = time.monotonic()
    async with _CACHE_LOCK:
        cached = _GAME_ID_CACHE.get(int(game_id))
        if cached and cached[0] > now:
            return cached[1]

    provider = SStatsProvider()
    home_id = away_id = None
    match_flash_id = None
    try:
        payload = await provider.get_game(int(game_id))
        obj = provider._payload_object(payload)
        match_flash_id = _clean_ls_id(_dict_value(obj, "flashId", "FlashId", "flashscoreId", "FlashscoreId"))
        if not match_flash_id:
            match_flash_id = _clean_ls_id(provider._deep_value(obj, "flashId", "FlashId", "flashscoreId", "FlashscoreId"))
    except Exception as exc:
        logger.warning("Oracle H2H: Games/%s lookup failed: %s", game_id, type(exc).__name__)

    if not match_flash_id:
        try:
            lookup = await provider._post(
                "Games/query",
                {"Condition": f"Id = {int(game_id)}", "Fields": ["Id", "FlashId"], "Limit": 1, "Format": "json", "Timezone": 0},
                timeout=2.0,
            )
            match_flash_id = _clean_ls_id(provider._deep_value(lookup, "flashId", "FlashId"))
        except Exception as exc:
            logger.warning("Oracle H2H: current game FlashId lookup failed: %s", type(exc).__name__)

    if match_flash_id:
        try:
            info = await provider.get_ls_game_info(match_flash_id)
            obj = provider._payload_object(info)
            home_id = _side_id_from_info(obj, "home", home_name, provider)
            away_id = _side_id_from_info(obj, "away", away_name, provider)
        except Exception as exc:
            logger.warning("Oracle H2H: Ls/GameInfo %s failed: %s", match_flash_id, type(exc).__name__)

    ttl = _GAME_ID_CACHE_TTL if home_id and away_id else _NEGATIVE_CACHE_TTL
    result = (home_id, away_id)
    async with _CACHE_LOCK:
        _GAME_ID_CACHE[int(game_id)] = (now + ttl, result)
    logger.warning(
        "Oracle H2H current-game mapping: game=%s flash=%s home=%s/%s away=%s/%s",
        game_id, match_flash_id, home_name, home_id, away_name, away_id,
    )
    return result


async def _resolve_ls_team_id(provider_id: int, team_name: str) -> str | None:
    cache_key = (int(provider_id), _norm(team_name))
    now = time.monotonic()
    async with _CACHE_LOCK:
        cached = _TEAM_ID_CACHE.get(cache_key)
        if cached and cached[0] > now:
            return cached[1]

    provider = SStatsProvider()
    resolved = None
    try:
        payload = await provider.get_team(int(provider_id))
        obj = provider._payload_object(payload)
        resolved = _preferred_ls_id(obj, provider)
    except Exception:
        pass

    if not resolved:
        for params in (
            {"Name": team_name, "Limit": 20, "Offset": 0},
            {"name": team_name, "Limit": 20, "Offset": 0},
            {"Search": team_name, "Limit": 20, "Offset": 0},
            {"Query": team_name, "Limit": 20, "Offset": 0},
        ):
            try:
                payload = await provider._get("Ls/Teams", params, timeout=2.5)
            except Exception:
                continue
            candidates = []
            for row in _rows(payload):
                name = provider._deep_value(row, "teamName", "TeamName", "name", "Name", "title", "Title")
                ident = _preferred_ls_id(row, provider)
                if ident:
                    candidates.append((_name_similarity(name, team_name), ident))
            if candidates:
                candidates.sort(reverse=True)
                if candidates[0][0] >= 0.65:
                    resolved = candidates[0][1]
                    break

    ttl = _TEAM_ID_CACHE_TTL if resolved else _NEGATIVE_CACHE_TTL
    async with _CACHE_LOCK:
        _TEAM_ID_CACHE[cache_key] = (now + ttl, resolved)
    return resolved


def _row_side_id(row: dict, provider: SStatsProvider, side: str) -> str | None:
    block = _find_side_block(row, side)
    candidate = _preferred_ls_id(block, provider)
    if candidate:
        return candidate
    direct_names = ("homeTeamId", "HomeTeamId") if side == "home" else ("awayTeamId", "AwayTeamId")
    direct = _clean_ls_id(provider._deep_value(row, *direct_names))
    return direct if _looks_flash_id(direct) else None


def _deep_first(provider: SStatsProvider, obj, *names):
    return provider._deep_value(obj, *names)


def _normalize_ls_h2h(payload, home_ls_id: str, away_ls_id: str, home_name: str, away_name: str, before: datetime) -> list[dict]:
    provider = SStatsProvider()
    before_utc = before if before.tzinfo else before.replace(tzinfo=timezone.utc)
    before_utc = before_utc.astimezone(timezone.utc)
    result = []

    for raw in _rows(payload):
        row = provider._normalize_game(raw)
        played_at = _parse_date(
            row.get("date") or row.get("Date") or _deep_first(
                provider, raw, "startTime", "StartTime", "startTimestamp", "StartTimestamp", "kickoffAt", "KickoffAt", "timestamp", "Timestamp"
            )
        )
        if played_at is None or played_at >= before_utc:
            continue

        home_score = _int_score(
            row.get("scoreHomeFT") if row.get("scoreHomeFT") is not None else
            row.get("ScoreHomeFT") if row.get("ScoreHomeFT") is not None else
            row.get("scoreHome") if row.get("scoreHome") is not None else
            row.get("ScoreHome") if row.get("ScoreHome") is not None else
            _deep_first(provider, raw, "homeFTResult", "HomeFTResult", "homeResult", "HomeResult", "homeScore", "HomeScore")
        )
        away_score = _int_score(
            row.get("scoreAwayFT") if row.get("scoreAwayFT") is not None else
            row.get("ScoreAwayFT") if row.get("ScoreAwayFT") is not None else
            row.get("scoreAway") if row.get("scoreAway") is not None else
            row.get("ScoreAway") if row.get("ScoreAway") is not None else
            _deep_first(provider, raw, "awayFTResult", "AwayFTResult", "awayResult", "AwayResult", "awayScore", "AwayScore")
        )
        if home_score is None or away_score is None:
            continue

        raw_home_name = str(row.get("homeTeamName") or row.get("HomeTeamName") or _deep_first(provider, _find_side_block(raw, "home") or {}, "name", "Name", "teamName", "TeamName") or "")
        raw_away_name = str(row.get("awayTeamName") or row.get("AwayTeamName") or _deep_first(provider, _find_side_block(raw, "away") or {}, "name", "Name", "teamName", "TeamName") or "")
        row_home_id = _row_side_id(raw, provider, "home")

        if row_home_id == _clean_ls_id(home_ls_id):
            display_home, display_away = home_name, away_name
        elif row_home_id == _clean_ls_id(away_ls_id):
            display_home, display_away = away_name, home_name
        else:
            direct = _name_similarity(raw_home_name, home_name) + _name_similarity(raw_away_name, away_name)
            reverse = _name_similarity(raw_home_name, away_name) + _name_similarity(raw_away_name, home_name)
            display_home, display_away = (away_name, home_name) if reverse > direct else (home_name, away_name)

        competition = str(_deep_first(provider, raw, "leagueName", "LeagueName", "competitionName", "CompetitionName", "tournamentName", "TournamentName") or "")
        result.append({
            "date": played_at.date().isoformat(),
            "home": display_home,
            "away": display_away,
            "score": f"{home_score}:{away_score}",
            "competition": competition,
            "source": "SStats / Flashscore",
            "_sort": played_at.timestamp(),
        })

    result.sort(key=lambda item: item["_sort"], reverse=True)
    for item in result:
        item.pop("_sort", None)
    return result[:_MAX_MATCHES]


async def _fetch_flashscore_h2h(game_id: int, home_provider_id: int, away_provider_id: int, home_name: str, away_name: str, before: datetime) -> list[dict]:
    # The current fixture is the safest mapping source: Ls/GameInfo contains the
    # exact two Flashscore teams participating in this match.
    home_ls_id, away_ls_id = await _resolve_ls_ids_from_current_game(game_id, home_name, away_name)
    if not home_ls_id or not away_ls_id:
        home_ls_id, away_ls_id = await asyncio.gather(
            _resolve_ls_team_id(home_provider_id, home_name),
            _resolve_ls_team_id(away_provider_id, away_name),
        )

    if not home_ls_id or not away_ls_id:
        logger.warning("Oracle H2H mapping missing: %s/%s - %s/%s", home_name, home_ls_id, away_name, away_ls_id)
        return []

    cache_key = tuple(sorted((_clean_ls_id(home_ls_id), _clean_ls_id(away_ls_id))))
    now = time.monotonic()
    async with _CACHE_LOCK:
        cached = _H2H_CACHE.get(cache_key)
        if cached and cached[0] > now:
            return [dict(row) for row in cached[1]]

    provider = SStatsProvider()
    rows = []
    raw_count = 0
    errors = []
    # First request exactly matches the example in the official SStats docs.
    for params in (
        {"BothTeams": f"{home_ls_id},{away_ls_id}"},
        {"BothTeams": f"{home_ls_id},{away_ls_id}", "Limit": 100},
        {"BothTeams": f"{home_ls_id},{away_ls_id}", "Ended": True, "Limit": 100, "TimeZone": 0},
    ):
        try:
            payload = await provider._get("Ls/List", params, timeout=4.5)
            extracted = _rows(payload)
            raw_count = max(raw_count, len(extracted))
            rows = _normalize_ls_h2h(payload, home_ls_id, away_ls_id, home_name, away_name, before)
            if rows:
                break
        except Exception as exc:
            errors.append(type(exc).__name__)

    ttl = _H2H_CACHE_TTL if rows else _NEGATIVE_CACHE_TTL
    async with _CACHE_LOCK:
        _H2H_CACHE[cache_key] = (now + ttl, [dict(row) for row in rows])
    logger.warning(
        "Oracle H2H Flashscore result: %s-%s ids=%s,%s raw=%s parsed=%s errors=%s",
        home_name, away_name, home_ls_id, away_ls_id, raw_count, len(rows), ",".join(errors) or "none",
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
        int(match.provider_id),
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
