from __future__ import annotations

import logging

import app.oracle_h2h_flashscore as flash_h2h

logger = logging.getLogger(__name__)
_INSTALLED = False
_ORIGINAL_NORMALIZE = None


def _direct_key(obj: dict, *names: str) -> bool:
    if not isinstance(obj, dict):
        return False
    wanted = {str(name).casefold() for name in names}
    return any(str(key).casefold() in wanted for key in obj)


def _looks_like_event(obj: dict) -> bool:
    if not isinstance(obj, dict):
        return False
    has_time = _direct_key(
        obj,
        "date",
        "startTime",
        "startTimestamp",
        "kickoffAt",
        "timestamp",
        "startDate",
        "utcDate",
    )
    has_home = _direct_key(
        obj,
        "homeTeam",
        "homeParticipant",
        "home",
        "team1",
        "participant1",
        "homeTeamName",
    )
    has_away = _direct_key(
        obj,
        "awayTeam",
        "awayParticipant",
        "away",
        "team2",
        "participant2",
        "awayTeamName",
    )
    has_score = _direct_key(
        obj,
        "homeScore",
        "awayScore",
        "scoreHome",
        "scoreAway",
        "scoreHomeFT",
        "scoreAwayFT",
        "homeResult",
        "awayResult",
        "homeFTResult",
        "awayFTResult",
    )
    # Finished Flashscore H2H events normally have time + two participants. Score
    # can be nested or absent at this level, so don't require it here.
    return bool(has_time and has_home and has_away) or bool(has_time and has_score and (has_home or has_away))


def _event_candidates(payload) -> list[dict]:
    result: list[dict] = []
    seen: set[int] = set()

    def walk(value):
        if isinstance(value, dict):
            marker = id(value)
            if marker in seen:
                return
            seen.add(marker)
            if _looks_like_event(value):
                result.append(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    return result


def _normalize_nested(payload, home_ls_id, away_ls_id, home_name, away_name, before):
    # Keep the provider's normal shape fast-path first.
    rows = _ORIGINAL_NORMALIZE(payload, home_ls_id, away_ls_id, home_name, away_name, before)
    if rows:
        return rows

    candidates = _event_candidates(payload)
    merged: list[dict] = []
    seen = set()
    for candidate in candidates:
        parsed = _ORIGINAL_NORMALIZE(
            {"data": [candidate]},
            home_ls_id,
            away_ls_id,
            home_name,
            away_name,
            before,
        )
        for row in parsed:
            key = (
                str(row.get("date") or ""),
                str(row.get("home") or "").casefold(),
                str(row.get("away") or "").casefold(),
                str(row.get("score") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(row)

    merged.sort(key=lambda row: str(row.get("date") or ""), reverse=True)
    if not merged:
        logger.warning(
            "Oracle H2H nested parser: %s-%s candidates=%s parsed=0",
            home_name,
            away_name,
            len(candidates),
        )
    else:
        logger.warning(
            "Oracle H2H nested parser: %s-%s candidates=%s parsed=%s",
            home_name,
            away_name,
            len(candidates),
            len(merged),
        )
    return merged[: flash_h2h._MAX_MATCHES]


async def _skip_broken_current_game_mapping(game_id: int, home_name: str, away_name: str):
    # Games/<id> may expose a nested team FlashId before a fixture FlashId. That
    # made the old resolver call Ls/GameInfo with a TEAM id. Team lookup through
    # Ls/Teams is the correct fallback and already resolves the two participants.
    return None, None


def install_flashscore_h2h_parser_patch() -> None:
    global _INSTALLED, _ORIGINAL_NORMALIZE
    if _INSTALLED:
        return
    _INSTALLED = True
    _ORIGINAL_NORMALIZE = flash_h2h._normalize_ls_h2h
    flash_h2h._normalize_ls_h2h = _normalize_nested
    flash_h2h._resolve_ls_ids_from_current_game = _skip_broken_current_game_mapping
