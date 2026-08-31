from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Match, Team, Tournament
from app.providers.sstats import SStatsProvider

SSTATS_PROVIDER = "sstats"
CHAMPIONS_LEAGUE_ID = 2


def _pick(data: dict, *names: str, default=None):
    for name in names:
        if name in data:
            return data[name]
    return default


def _parse_datetime(value) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        result = datetime.fromisoformat(text)
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result


async def _get_or_create_tournament(session: AsyncSession, item: dict) -> Tournament:
    provider_id = int(_pick(item, "leagueId", "LeagueId", default=CHAMPIONS_LEAGUE_ID))
    tournament = await session.scalar(
        select(Tournament).where(
            Tournament.provider == SSTATS_PROVIDER,
            Tournament.provider_id == provider_id,
        )
    )
    name = _pick(item, "leagueName", "LeagueName", default="UEFA Champions League")
    if tournament is None:
        tournament = Tournament(provider=SSTATS_PROVIDER, provider_id=provider_id, name=name)
        session.add(tournament)
        await session.flush()

    tournament.name = name
    tournament.country = _pick(item, "countryName", "CountryName")
    return tournament


async def _get_or_create_team(session: AsyncSession, provider_id: int, name: str) -> Team:
    team = await session.scalar(
        select(Team).where(
            Team.provider == SSTATS_PROVIDER,
            Team.provider_id == provider_id,
        )
    )
    if team is None:
        team = Team(provider=SSTATS_PROVIDER, provider_id=provider_id, name=name)
        session.add(team)
        await session.flush()
    team.name = name
    return team


async def sync_sstats_champions_league(session: AsyncSession, year: int) -> dict:
    payload = await SStatsProvider().query_games(CHAMPIONS_LEAGUE_ID, year)
    items = payload.get("data") or payload.get("response") or []

    created = 0
    updated = 0
    skipped = 0
    skip_reasons: dict[str, int] = {}

    for item in items:
        game_id = _pick(item, "id", "Id")
        home_id = _pick(item, "homeTeamId", "HomeTeamId")
        away_id = _pick(item, "awayTeamId", "AwayTeamId")
        home_name = _pick(item, "homeTeamName", "HomeTeamName")
        away_name = _pick(item, "awayTeamName", "AwayTeamName")
        date_value = _pick(item, "date", "Date")

        required = {
            "game_id": game_id,
            "home_id": home_id,
            "away_id": away_id,
            "home_name": home_name,
            "away_name": away_name,
            "date": date_value,
        }
        missing = [key for key, value in required.items() if value is None]
        if missing:
            skipped += 1
            reason = ",".join(missing)
            skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
            continue

        tournament = await _get_or_create_tournament(session, item)
        home_team = await _get_or_create_team(session, int(home_id), str(home_name))
        away_team = await _get_or_create_team(session, int(away_id), str(away_name))

        match = await session.scalar(
            select(Match).where(
                Match.provider == SSTATS_PROVIDER,
                Match.provider_id == int(game_id),
            )
        )
        is_new = match is None
        kickoff_at = _parse_datetime(date_value)
        status = _pick(item, "status", "Status")

        if is_new:
            match = Match(
                provider=SSTATS_PROVIDER,
                provider_id=int(game_id),
                tournament_id=tournament.id,
                season=int(_pick(item, "year", "Year", default=year)),
                kickoff_at=kickoff_at,
                status_short=f"S{status}" if status is not None else "S?",
                home_team_id=home_team.id,
                away_team_id=away_team.id,
            )
            session.add(match)

        match.tournament_id = tournament.id
        match.season = int(_pick(item, "year", "Year", default=year))
        match.round_name = _pick(item, "round", "Round", "roundName", "RoundName")
        match.kickoff_at = kickoff_at
        match.status_short = f"S{status}" if status is not None else "S?"
        match.status_long = f"SStats status {status}" if status is not None else None
        match.elapsed = None
        match.home_team_id = home_team.id
        match.away_team_id = away_team.id
        match.home_goals = _pick(item, "scoreHome", "ScoreHome", "scoreHomeFT", "ScoreHomeFT")
        match.away_goals = _pick(item, "scoreAway", "ScoreAway", "scoreAwayFT", "ScoreAwayFT")
        match.updated_at = datetime.now(timezone.utc)

        if is_new:
            created += 1
        else:
            updated += 1

    await session.commit()
    return {
        "provider": SSTATS_PROVIDER,
        "league_id": CHAMPIONS_LEAGUE_ID,
        "year": year,
        "received": len(items),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "skip_reasons": skip_reasons,
    }
