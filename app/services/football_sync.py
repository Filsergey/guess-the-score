from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Match, Team, Tournament
from app.providers.api_football import APIFootballProvider

CHAMPIONS_LEAGUE_ID = 2


async def _get_or_create_tournament(session: AsyncSession, league_data: dict) -> Tournament:
    provider_id = league_data["id"]
    tournament = await session.scalar(select(Tournament).where(Tournament.provider_id == provider_id))
    if tournament is None:
        tournament = Tournament(provider_id=provider_id, name=league_data["name"])
        session.add(tournament)
        await session.flush()

    tournament.name = league_data["name"]
    tournament.logo_url = league_data.get("logo")
    return tournament


async def _get_or_create_team(session: AsyncSession, team_data: dict) -> Team:
    provider_id = team_data["id"]
    team = await session.scalar(select(Team).where(Team.provider_id == provider_id))
    if team is None:
        team = Team(provider_id=provider_id, name=team_data["name"])
        session.add(team)
        await session.flush()

    team.name = team_data["name"]
    team.code = team_data.get("code")
    team.logo_url = team_data.get("logo")
    return team


async def sync_champions_league(session: AsyncSession, season: int) -> dict:
    provider = APIFootballProvider()
    payload = await provider.get_fixtures(CHAMPIONS_LEAGUE_ID, season)
    fixtures = payload.get("response", [])

    created = 0
    updated = 0

    for item in fixtures:
        fixture = item["fixture"]
        league = item["league"]
        teams = item["teams"]
        goals = item.get("goals", {})

        tournament = await _get_or_create_tournament(session, league)
        tournament.country = league.get("country")
        home_team = await _get_or_create_team(session, teams["home"])
        away_team = await _get_or_create_team(session, teams["away"])

        match = await session.scalar(select(Match).where(Match.provider_id == fixture["id"]))
        is_new = match is None
        if is_new:
            match = Match(
                provider_id=fixture["id"],
                tournament_id=tournament.id,
                season=season,
                kickoff_at=datetime.fromisoformat(fixture["date"]),
                status_short=fixture["status"]["short"],
                home_team_id=home_team.id,
                away_team_id=away_team.id,
            )
            session.add(match)

        match.tournament_id = tournament.id
        match.season = season
        match.round_name = league.get("round")
        match.kickoff_at = datetime.fromisoformat(fixture["date"])
        match.status_short = fixture["status"]["short"]
        match.status_long = fixture["status"].get("long")
        match.elapsed = fixture["status"].get("elapsed")
        match.home_team_id = home_team.id
        match.away_team_id = away_team.id
        match.home_goals = goals.get("home")
        match.away_goals = goals.get("away")
        match.updated_at = datetime.now(match.kickoff_at.tzinfo)

        if is_new:
            created += 1
        else:
            updated += 1

    await session.commit()
    return {
        "league_id": CHAMPIONS_LEAGUE_ID,
        "season": season,
        "received": len(fixtures),
        "created": created,
        "updated": updated,
    }
