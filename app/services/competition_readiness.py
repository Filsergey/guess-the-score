import asyncio
import math

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import Match, Player, Team, Tournament
from app.players import sync_sstats_team_players
from app.providers.sstats import SStatsProvider
from app.services.competition_prepare import (
    _hydrate_missing_logos_from_api_football,
    prepare_sstats_competition,
)
from app.services.sstats_sync import SSTATS_PROVIDER


_background_tasks: set[asyncio.Task] = set()


def _allowed_missing(total_teams: int) -> int:
    """A small gap means roughly 10% of clubs, but never more than two clubs."""
    if total_teams <= 0:
        return 0
    return min(2, max(1, math.ceil(total_teams * 0.10)))


async def _competition_teams(session, league_id: int, year: int):
    tournament = await session.scalar(
        select(Tournament).where(
            Tournament.provider == SSTATS_PROVIDER,
            Tournament.provider_id == int(league_id),
        )
    )
    if tournament is None:
        return None, []

    matches = (
        await session.execute(
            select(Match).where(
                Match.provider == SSTATS_PROVIDER,
                Match.tournament_id == tournament.id,
                Match.season == int(year),
            )
        )
    ).scalars().all()
    team_ids = {
        team_id
        for match in matches
        for team_id in (match.home_team_id, match.away_team_id)
        if team_id is not None
    }
    if not team_ids:
        return tournament, []
    teams = (
        await session.execute(select(Team).where(Team.id.in_(team_ids)).order_by(Team.name))
    ).scalars().all()
    return tournament, teams


async def _player_count(session, team: Team, year: int) -> int:
    value = await session.scalar(
        select(func.count(Player.id)).where(
            Player.provider == SSTATS_PROVIDER,
            Player.is_active.is_(True),
            Player.team_provider_id == team.provider_id,
            Player.season == int(year),
        )
    )
    return int(value or 0)


async def _readiness_snapshot(session, league_id: int, year: int) -> dict:
    tournament, teams = await _competition_teams(session, league_id, year)
    counts = {int(team.id): await _player_count(session, team, year) for team in teams}
    missing_players = [team for team in teams if counts.get(int(team.id), 0) < 11]
    missing_logos = [
        team
        for team in teams
        if not team.logo_url or not str(team.logo_url).startswith(("http://", "https://"))
    ]
    return {
        "tournament": tournament,
        "teams": teams,
        "counts": counts,
        "missing_players": missing_players,
        "missing_logos": missing_logos,
        "allowed_missing": _allowed_missing(len(teams)),
    }


async def _background_fill_missing_players(team_ids: list[int], year: int) -> None:
    if not team_ids:
        return
    for delay in (5, 60, 300, 900):
        await asyncio.sleep(delay)
        async with SessionLocal() as session:
            teams = (
                await session.execute(select(Team).where(Team.id.in_(team_ids)).order_by(Team.name))
            ).scalars().all()
            pending = []
            for team in teams:
                if await _player_count(session, team, year) < 11:
                    pending.append(team)
            if not pending:
                return

            provider = SStatsProvider()
            anonymous = not bool(provider.settings.sstats_api_key)
            for index, team in enumerate(pending):
                try:
                    await sync_sstats_team_players(session, team, year)
                except Exception:
                    await session.rollback()
                if anonymous and index < len(pending) - 1:
                    await asyncio.sleep(2.5)


def _schedule_player_background(team_ids: list[int], year: int) -> None:
    if not team_ids:
        return
    task = asyncio.create_task(_background_fill_missing_players(team_ids, year))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def prepare_sstats_competition_tolerant(session, league_id: int, year: int, league_name: str):
    """Attempt a complete preload, but tolerate only a small residual gap.

    We still wait while matches, team metadata, crests and player rosters are fetched for
    every participating club. Creation is allowed only when at most ~10% (max two clubs)
    still miss a crest or a usable player roster. Those few gaps continue in background.
    """
    strict_result = None
    strict_error = None
    try:
        strict_result = await prepare_sstats_competition(session, league_id, year, league_name)
    except Exception as exc:
        strict_error = exc
        await session.rollback()
        text = str(exc).lower()
        # Only partial roster failures may be tolerated. Match/team failures stay blocking.
        if "игрок" not in text and "каталог" not in text:
            raise

    snapshot = await _readiness_snapshot(session, league_id, year)
    teams = snapshot["teams"]
    tournament = snapshot["tournament"]
    if tournament is None or len(teams) < 2:
        if strict_error:
            raise strict_error
        raise RuntimeError("Турнир подготовлен не полностью")

    # Before deciding that crests are missing, make one foreground fallback pass.
    if snapshot["missing_logos"]:
        try:
            await _hydrate_missing_logos_from_api_football(session, snapshot["missing_logos"])
        except Exception:
            await session.rollback()
        snapshot = await _readiness_snapshot(session, league_id, year)

    allowed = snapshot["allowed_missing"]
    missing_players = snapshot["missing_players"]
    missing_logos = snapshot["missing_logos"]

    if len(missing_players) > allowed:
        preview = ", ".join(team.name for team in missing_players[:5])
        suffix = "…" if len(missing_players) > 5 else ""
        raise RuntimeError(
            f"Массовая загрузка игроков завершена не полностью: "
            f"нет составов у {len(missing_players)} из {len(teams)} команд ({preview}{suffix})"
        )

    if len(missing_logos) > allowed:
        preview = ", ".join(team.name for team in missing_logos[:5])
        suffix = "…" if len(missing_logos) > 5 else ""
        raise RuntimeError(
            f"Массовая загрузка логотипов завершена не полностью: "
            f"нет эмблем у {len(missing_logos)} из {len(teams)} команд ({preview}{suffix})"
        )

    if missing_players:
        _schedule_player_background([int(team.id) for team in missing_players], int(year))

    result = dict(strict_result or {})
    result.update(
        {
            "status": "ready",
            "tournament_id": int(tournament.id),
            "teams_ready": len(teams),
            "team_logos_ready": len(teams) - len(missing_logos),
            "team_logos_pending": [team.name for team in missing_logos],
            "teams_with_players": len(teams) - len(missing_players),
            "players_pending": [team.name for team in missing_players],
            "allowed_missing_teams": allowed,
            "partial_metadata_allowed": bool(missing_players or missing_logos),
            "player_background_scheduled": bool(missing_players),
        }
    )
    return result
