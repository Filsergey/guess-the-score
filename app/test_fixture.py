import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import LeagueMember, Match, OraclePrediction, Prediction, Team, Tournament, User, UserLeague

router = APIRouter(tags=["test-fixture"])

TEST_LEAGUE_NAME = "🧪 Тест: достижения + LIVE"
TEST_TOURNAMENT_PROVIDER_ID = 990001
TEST_HOME_PROVIDER_ID = 990011
TEST_AWAY_PROVIDER_ID = 990012
TEST_MATCH_BASE_PROVIDER_ID = 991000


async def _get_or_create_team(db: AsyncSession, provider_id: int, name: str, code: str) -> Team:
    team = await db.scalar(select(Team).where(Team.provider == "test", Team.provider_id == provider_id))
    if team is None:
        team = Team(provider="test", provider_id=provider_id, name=name, source_name=name, code=code)
        db.add(team)
        await db.flush()
    return team


@router.post("/test-fixture")
async def create_test_fixture(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "superadmin":
        raise HTTPException(403, "Test fixture is available only to superadmin")

    now = datetime.now(timezone.utc)
    tournament = await db.scalar(select(Tournament).where(Tournament.provider == "test", Tournament.provider_id == TEST_TOURNAMENT_PROVIDER_ID))
    if tournament is None:
        tournament = Tournament(provider="test", provider_id=TEST_TOURNAMENT_PROVIDER_ID, name="Тестовый турнир", country="TEST")
        db.add(tournament)
        await db.flush()

    home = await _get_or_create_team(db, TEST_HOME_PROVIDER_ID, "Тест Юнайтед", "TST")
    away = await _get_or_create_team(db, TEST_AWAY_PROVIDER_ID, "Демо Сити", "DMO")

    league = await db.scalar(select(UserLeague).where(UserLeague.owner_user_id == user.id, UserLeague.name == TEST_LEAGUE_NAME))
    if league is None:
        league = UserLeague(
            name=TEST_LEAGUE_NAME,
            invite_code=f"TEST{user.id}"[-12:],
            owner_user_id=user.id,
            tournament_provider="test",
            tournament_season=now.year,
            tournament_id=tournament.id,
            is_private=True,
            include_oracle=True,
            created_at=now,
        )
        db.add(league)
        await db.flush()
        db.add(LeagueMember(league_id=league.id, user_id=user.id, role="owner", joined_at=now))
    else:
        league.tournament_provider = "test"
        league.tournament_season = now.year
        league.tournament_id = tournament.id
        league.include_oracle = True
        member = await db.scalar(select(LeagueMember).where(LeagueMember.league_id == league.id, LeagueMember.user_id == user.id))
        if member is None:
            db.add(LeagueMember(league_id=league.id, user_id=user.id, role="owner", joined_at=now))

    completed_ids = []
    for i in range(10):
        provider_id = TEST_MATCH_BASE_PROVIDER_ID + i
        match = await db.scalar(select(Match).where(Match.provider == "test", Match.provider_id == provider_id))
        kickoff = now - timedelta(minutes=30 - i)
        if match is None:
            match = Match(
                provider="test",
                provider_id=provider_id,
                tournament_id=tournament.id,
                season=now.year,
                round_name=f"Тестовый тур {i // 2 + 1}",
                kickoff_at=kickoff,
                status_short="FT",
                status_long="Finished",
                elapsed=90,
                home_team_id=home.id,
                away_team_id=away.id,
                home_goals=1,
                away_goals=0,
                updated_at=now,
            )
            db.add(match)
            await db.flush()
        else:
            match.tournament_id = tournament.id
            match.season = now.year
            match.round_name = f"Тестовый тур {i // 2 + 1}"
            match.kickoff_at = kickoff
            match.status_short = "FT"
            match.status_long = "Finished"
            match.elapsed = 90
            match.home_team_id = home.id
            match.away_team_id = away.id
            match.home_goals = 1
            match.away_goals = 0
            match.updated_at = now
        completed_ids.append(match.id)

        prediction = await db.scalar(select(Prediction).where(Prediction.user_id == user.id, Prediction.match_id == match.id))
        if prediction is None:
            db.add(Prediction(user_id=user.id, match_id=match.id, home_score=1, away_score=0, created_at=kickoff - timedelta(hours=2), updated_at=kickoff - timedelta(hours=2)))
        else:
            prediction.home_score = 1
            prediction.away_score = 0
            prediction.created_at = kickoff - timedelta(hours=2)
            prediction.updated_at = kickoff - timedelta(hours=2)

        oracle = await db.scalar(select(OraclePrediction).where(OraclePrediction.match_id == match.id))
        payload = json.dumps({"home_score": 0, "away_score": 0}, ensure_ascii=False)
        if oracle is None:
            db.add(OraclePrediction(match_id=match.id, payload_json=payload, source="test", generated_at=kickoff - timedelta(hours=1), updated_at=kickoff - timedelta(hours=1)))
        else:
            oracle.payload_json = payload
            oracle.source = "test"
            oracle.generated_at = kickoff - timedelta(hours=1)
            oracle.updated_at = kickoff - timedelta(hours=1)

    live_provider_id = TEST_MATCH_BASE_PROVIDER_ID + 100
    live = await db.scalar(select(Match).where(Match.provider == "test", Match.provider_id == live_provider_id))
    live_kickoff = now - timedelta(minutes=67)
    if live is None:
        live = Match(
            provider="test",
            provider_id=live_provider_id,
            tournament_id=tournament.id,
            season=now.year,
            round_name="LIVE · Тестовый матч",
            kickoff_at=live_kickoff,
            status_short="2H",
            status_long="Second Half",
            elapsed=67,
            home_team_id=home.id,
            away_team_id=away.id,
            home_goals=2,
            away_goals=1,
            updated_at=now,
        )
        db.add(live)
        await db.flush()
    else:
        live.tournament_id = tournament.id
        live.season = now.year
        live.round_name = "LIVE · Тестовый матч"
        live.kickoff_at = live_kickoff
        live.status_short = "2H"
        live.status_long = "Second Half"
        live.elapsed = 67
        live.home_team_id = home.id
        live.away_team_id = away.id
        live.home_goals = 2
        live.away_goals = 1
        live.updated_at = now

    await db.commit()
    return {
        "ok": True,
        "league_id": league.id,
        "league_name": league.name,
        "completed_matches": len(completed_ids),
        "live_match_id": live.id,
        "live_elapsed": live.elapsed,
        "achievement_fixture": {
            "sniper": 10,
            "exact_streak": 10,
            "hit_streak": 10,
            "oracle_wins": 10,
            "unique_exacts": 10,
            "round_wins": 5,
            "perfect_rounds": 5,
        },
    }
