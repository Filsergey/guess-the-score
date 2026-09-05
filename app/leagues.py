import secrets
import string
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import LeagueMember, User, UserLeague

router = APIRouter(prefix="/api/leagues", tags=["leagues"])


class LeagueCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    tournament_provider: str = Field(default="sstats", max_length=32)
    tournament_season: int = Field(default=2026, ge=2020, le=2100)
    is_private: bool = True
    include_oracle: bool = True


class LeagueJoin(BaseModel):
    invite_code: str = Field(min_length=4, max_length=12)


def _invite_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def serialize_league(league: UserLeague, member_role: str, member_count: int) -> dict:
    return {
        "id": league.id,
        "name": league.name,
        "invite_code": league.invite_code,
        "owner_user_id": league.owner_user_id,
        "member_role": member_role,
        "member_count": member_count,
        "tournament_provider": league.tournament_provider,
        "tournament_season": league.tournament_season,
        "is_private": league.is_private,
        "include_oracle": league.include_oracle,
        "created_at": league.created_at,
    }


async def _unique_invite_code(db: AsyncSession) -> str:
    for _ in range(10):
        code = _invite_code()
        existing = await db.scalar(select(UserLeague.id).where(UserLeague.invite_code == code))
        if existing is None:
            return code
    raise HTTPException(status_code=503, detail="Could not generate league invite code")


@router.get("/mine")
async def my_leagues(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    count_subquery = (
        select(LeagueMember.league_id, func.count(LeagueMember.id).label("member_count"))
        .group_by(LeagueMember.league_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(UserLeague, LeagueMember.role, count_subquery.c.member_count)
            .join(LeagueMember, LeagueMember.league_id == UserLeague.id)
            .outerjoin(count_subquery, count_subquery.c.league_id == UserLeague.id)
            .where(LeagueMember.user_id == user.id)
            .order_by(UserLeague.created_at)
        )
    ).all()
    items = [serialize_league(league, role, int(count or 0)) for league, role, count in rows]
    return {"count": len(items), "response": items}


@router.post("")
async def create_league(body: LeagueCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    name = body.name.strip()
    if len(name) < 2:
        raise HTTPException(status_code=422, detail="League name is too short")
    now = datetime.now(timezone.utc)
    league = UserLeague(
        name=name,
        invite_code=await _unique_invite_code(db),
        owner_user_id=user.id,
        tournament_provider=body.tournament_provider,
        tournament_season=body.tournament_season,
        is_private=body.is_private,
        include_oracle=body.include_oracle,
        created_at=now,
    )
    db.add(league)
    await db.flush()
    db.add(LeagueMember(league_id=league.id, user_id=user.id, role="owner", joined_at=now))
    await db.commit()
    await db.refresh(league)
    return serialize_league(league, "owner", 1)


@router.post("/join")
async def join_league(body: LeagueJoin, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    code = body.invite_code.strip().upper()
    league = await db.scalar(select(UserLeague).where(UserLeague.invite_code == code))
    if league is None:
        raise HTTPException(status_code=404, detail="League not found")
    membership = await db.scalar(
        select(LeagueMember).where(LeagueMember.league_id == league.id, LeagueMember.user_id == user.id)
    )
    if membership is None:
        membership = LeagueMember(league_id=league.id, user_id=user.id, role="member", joined_at=datetime.now(timezone.utc))
        db.add(membership)
        await db.commit()
    count = await db.scalar(select(func.count(LeagueMember.id)).where(LeagueMember.league_id == league.id))
    return serialize_league(league, membership.role, int(count or 0))


@router.get("/{league_id}/members")
async def league_members(league_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    membership = await db.scalar(
        select(LeagueMember).where(LeagueMember.league_id == league_id, LeagueMember.user_id == user.id)
    )
    if membership is None and user.role != "superadmin":
        raise HTTPException(status_code=403, detail="You are not a member of this league")
    league = await db.get(UserLeague, league_id)
    if league is None:
        raise HTTPException(status_code=404, detail="League not found")
    rows = (
        await db.execute(
            select(LeagueMember, User)
            .join(User, User.id == LeagueMember.user_id)
            .where(LeagueMember.league_id == league_id)
            .order_by(LeagueMember.joined_at)
        )
    ).all()
    items = [
        {
            "user_id": member.user_id,
            "display_name": member_user.display_name,
            "username": member_user.username,
            "avatar_url": member_user.avatar_url,
            "role": member.role,
            "joined_at": member.joined_at,
        }
        for member, member_user in rows
    ]
    return {"league": serialize_league(league, membership.role if membership else "superadmin", len(items)), "count": len(items), "response": items}
