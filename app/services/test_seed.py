from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.match_status import FINAL_MATCH_STATUSES
from app.models import LeagueMember, Match, Prediction, User, UserLeague

TEST_TELEGRAM_ID = -990000000001
TEST_USERNAME = "reaction_tester"
TEST_DISPLAY_NAME = "Вася Тестовый"


async def ensure_test_reaction_participant(db: AsyncSession) -> dict:
    """Create one idempotent fake participant with predictions in completed matches.

    The seed only touches leagues whose name contains "тест" or "test" and exists so
    reactions/comments can be checked safely without polluting normal leagues.
    """
    leagues = (await db.scalars(
        select(UserLeague)
        .where(or_(UserLeague.name.ilike("%тест%"), UserLeague.name.ilike("%test%")))
        .order_by(UserLeague.id)
    )).all()
    if not leagues:
        return {"seeded": False, "reason": "test_league_not_found"}

    user = await db.scalar(select(User).where(User.telegram_id == TEST_TELEGRAM_ID))
    created_user = False
    if user is None:
        user = User(
            telegram_id=TEST_TELEGRAM_ID,
            username=TEST_USERNAME,
            display_name=TEST_DISPLAY_NAME,
            role="user",
            registered_at=datetime.now(timezone.utc),
            last_login_at=datetime.now(timezone.utc),
        )
        db.add(user)
        await db.flush()
        created_user = True

    memberships = 0
    predictions = 0
    touched = []
    for league in leagues:
        member = await db.scalar(select(LeagueMember).where(
            LeagueMember.league_id == league.id,
            LeagueMember.user_id == user.id,
        ))
        if member is None:
            db.add(LeagueMember(
                league_id=league.id,
                user_id=user.id,
                role="member",
                joined_at=datetime.now(timezone.utc),
            ))
            memberships += 1

        q = select(Match).where(
            Match.provider == league.tournament_provider,
            Match.season == league.tournament_season,
            Match.status_short.in_(tuple(FINAL_MATCH_STATUSES)),
            Match.home_goals.is_not(None),
            Match.away_goals.is_not(None),
        )
        if league.tournament_id is not None:
            q = q.where(Match.tournament_id == league.tournament_id)
        matches = (await db.scalars(q.order_by(Match.kickoff_at.desc()).limit(10))).all()

        for index, match in enumerate(reversed(matches)):
            exists = await db.scalar(select(Prediction.id).where(
                Prediction.user_id == user.id,
                Prediction.match_id == match.id,
            ))
            if exists is not None:
                continue
            hg = int(match.home_goals or 0)
            ag = int(match.away_goals or 0)
            mode = index % 4
            if mode == 0:
                ph, pa = hg, ag
            elif mode == 1:
                ph, pa = max(0, hg + 1), ag
            elif mode == 2:
                ph, pa = ag, hg
            else:
                ph, pa = 2, 1
            db.add(Prediction(
                user_id=user.id,
                match_id=match.id,
                home_score=ph,
                away_score=pa,
                created_at=match.kickoff_at,
                updated_at=match.kickoff_at,
            ))
            predictions += 1
        touched.append({"league_id": league.id, "league_name": league.name, "finished_matches": len(matches)})

    await db.commit()
    return {
        "seeded": True,
        "user_id": user.id,
        "display_name": user.display_name,
        "created_user": created_user,
        "memberships_added": memberships,
        "predictions_added": predictions,
        "leagues": touched,
    }
