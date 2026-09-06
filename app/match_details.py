from typing import Any


def _pick(obj: dict | None, *names: str):
    if not isinstance(obj, dict):
        return None
    for name in names:
        if name in obj:
            return obj[name]
    return None


def _player(player: dict | None) -> dict | None:
    if not isinstance(player, dict):
        return None
    return {
        "id": _pick(player, "id", "Id"),
        "name": _pick(player, "name", "Name", "playerName", "PlayerName"),
    }


def _event(row: dict) -> dict:
    return {
        "id": _pick(row, "id", "Id"),
        "team_id": _pick(row, "teamId", "TeamId"),
        "elapsed": _pick(row, "elapsed", "Elapsed"),
        "extra": _pick(row, "extra", "Extra"),
        "type": _pick(row, "type", "Type"),
        "name": _pick(row, "name", "Name"),
        "player": _player(_pick(row, "player", "Player")),
        "assist_player": _player(_pick(row, "assistPlayer", "AssistPlayer")),
    }


def _lineup_player(row: dict) -> dict:
    return {
        "team_id": _pick(row, "teamId", "TeamId"),
        "player_id": _pick(row, "playerId", "PlayerId"),
        "name": _pick(row, "playerName", "PlayerName"),
        "number": _pick(row, "number", "Number"),
        "position": _pick(row, "position", "Position"),
        "grid": _pick(row, "grid", "Grid"),
        "start_xi": bool(_pick(row, "startXI", "StartXI")),
    }


def _live_snapshot(full: dict) -> dict:
    game = _pick(full, "game", "Game")
    game = game if isinstance(game, dict) else full
    return {
        "status": _pick(game, "status", "Status"),
        "status_name": _pick(game, "statusName", "StatusName", "statusText", "StatusText"),
        "elapsed": _pick(game, "elapsed", "Elapsed", "minute", "Minute"),
        "home_goals": _pick(game, "scoreHome", "ScoreHome", "homeResult", "HomeResult"),
        "away_goals": _pick(game, "scoreAway", "ScoreAway", "awayResult", "AwayResult"),
    }


def normalize_full_match(full: dict | None, home_team_id: int | None, away_team_id: int | None) -> dict[str, Any]:
    """Return stable SStats full-match fields used by the client."""
    full = full if isinstance(full, dict) else {}
    lineup = _pick(full, "lineups", "Lineups") or {}
    events = [_event(x) for x in (_pick(full, "events", "Events") or []) if isinstance(x, dict)]
    events.sort(key=lambda x: (int(x["elapsed"] or 0), int(x["extra"] or 0), int(x["id"] or 0)))
    players = [_lineup_player(x) for x in (_pick(full, "lineupPlayers", "LineupPlayers") or []) if isinstance(x, dict)]

    def side(team_id: int | None, formation: Any):
        side_players = [x for x in players if str(x.get("team_id")) == str(team_id)]
        return {
            "formation": formation,
            "starting": [x for x in side_players if x["start_xi"]],
            "bench": [x for x in side_players if not x["start_xi"]],
        }

    venue = _pick(full, "venue", "Venue") or {}
    return {
        "live_raw": _live_snapshot(full),
        "referee": _pick(full, "refereeName", "RefereeName"),
        "venue_full": {
            "id": _pick(venue, "id", "Id"),
            "name": _pick(venue, "name", "Name"),
            "city": _pick(venue, "city", "City"),
            "address": _pick(venue, "address", "Address"),
        } if venue else None,
        "events": events,
        "lineups": {
            "home": side(home_team_id, _pick(lineup, "homeFormation", "HomeFormation")),
            "away": side(away_team_id, _pick(lineup, "awayFormation", "AwayFormation")),
        },
    }
