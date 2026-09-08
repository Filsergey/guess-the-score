from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.auth import get_current_user
from app.database import get_db
from app.leagues import _membership
from app.models import Base, LeagueMember, Match, User, UserLeague

router = APIRouter(prefix="/api/leagues", tags=["league-social"])

REACTION_KINDS = {"laugh", "fire", "clown", "bold", "oracle", "respect"}


class LeagueReaction(Base):
    __tablename__ = "league_reactions"
    __table_args__ = (
        UniqueConstraint("league_id", "from_user_id", "target_user_id", "kind", name="uq_league_reaction_once"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("user_leagues.id", ondelete="CASCADE"), index=True)
    from_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    target_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class MatchReaction(Base):
    __tablename__ = "match_reactions"
    __table_args__ = (
        UniqueConstraint(
            "league_id", "match_id", "from_user_id", "target_user_id", "kind",
            name="uq_match_reaction_once",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("user_leagues.id", ondelete="CASCADE"), index=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    from_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    target_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class ReactionBody(BaseModel):
    target_user_id: int = Field(ge=1)
    kind: str = Field(min_length=2, max_length=24)


async def _target_member(league_id: int, target_user_id: int, db: AsyncSession) -> User:
    row = (await db.execute(
        select(User).join(LeagueMember, LeagueMember.user_id == User.id).where(
            LeagueMember.league_id == league_id,
            User.id == target_user_id,
        )
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Участник не найден в этой лиге")
    return row


async def _started_match(league_id: int, match_id: int, db: AsyncSession) -> tuple[UserLeague, Match]:
    league = await db.get(UserLeague, league_id)
    match = await db.get(Match, match_id)
    if league is None:
        raise HTTPException(404, "Лига не найдена")
    if match is None:
        raise HTTPException(404, "Матч не найден")
    belongs = match.provider == league.tournament_provider and match.season == league.tournament_season
    if league.tournament_id is not None:
        belongs = belongs and match.tournament_id == league.tournament_id
    if not belongs:
        raise HTTPException(409, "Матч не относится к турниру этой лиги")
    kickoff = match.kickoff_at
    if kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) < kickoff:
        raise HTTPException(409, "Реакции откроются после начала матча")
    return league, match


@router.get("/{league_id}/matches/{match_id}/reactions")
async def match_reactions(
    league_id: int,
    match_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _membership(league_id, user, db)
    await _started_match(league_id, match_id, db)
    rows = (await db.scalars(select(MatchReaction).where(
        MatchReaction.league_id == league_id,
        MatchReaction.match_id == match_id,
    ).order_by(MatchReaction.created_at.desc()))).all()
    targets: dict[str, dict] = {}
    for item in rows:
        target = targets.setdefault(str(item.target_user_id), {"counts": {}, "mine": []})
        target["counts"][item.kind] = int(target["counts"].get(item.kind, 0)) + 1
        if item.from_user_id == user.id:
            target["mine"].append(item.kind)
    for target in targets.values():
        target["mine"].sort()
    return {"league_id": league_id, "match_id": match_id, "targets": targets}


@router.post("/{league_id}/matches/{match_id}/reactions")
async def toggle_match_reaction(
    league_id: int,
    match_id: int,
    body: ReactionBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _membership(league_id, user, db)
    await _started_match(league_id, match_id, db)
    kind = body.kind.strip().lower()
    if kind not in REACTION_KINDS:
        raise HTTPException(422, "Неизвестная реакция")
    if body.target_user_id == user.id:
        raise HTTPException(422, "Себя подколоть можно и без приложения")
    await _target_member(league_id, body.target_user_id, db)
    existing = await db.scalar(select(MatchReaction).where(
        MatchReaction.league_id == league_id,
        MatchReaction.match_id == match_id,
        MatchReaction.from_user_id == user.id,
        MatchReaction.target_user_id == body.target_user_id,
        MatchReaction.kind == kind,
    ))
    if existing is not None:
        await db.delete(existing)
        await db.commit()
        return {"ok": True, "active": False, "kind": kind}
    db.add(MatchReaction(
        league_id=league_id,
        match_id=match_id,
        from_user_id=user.id,
        target_user_id=body.target_user_id,
        kind=kind,
        created_at=datetime.now(timezone.utc),
    ))
    await db.commit()
    return {"ok": True, "active": True, "kind": kind}


@router.get("/{league_id}/reactions")
async def league_reactions(
    league_id: int,
    target_user_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=30, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _membership(league_id, user, db)
    league = await db.get(UserLeague, league_id)
    if league is None:
        raise HTTPException(404, "Лига не найдена")
    if target_user_id is not None:
        await _target_member(league_id, target_user_id, db)

    q = select(LeagueReaction).where(LeagueReaction.league_id == league_id)
    if target_user_id is not None:
        q = q.where(LeagueReaction.target_user_id == target_user_id)
    rows = (await db.scalars(q.order_by(LeagueReaction.created_at.desc()).limit(limit))).all()

    user_ids = {x.from_user_id for x in rows} | {x.target_user_id for x in rows}
    users = (await db.scalars(select(User).where(User.id.in_(user_ids)))).all() if user_ids else []
    by_user = {x.id: x for x in users}

    counts_q = select(LeagueReaction.kind, func.count(LeagueReaction.id)).where(LeagueReaction.league_id == league_id)
    if target_user_id is not None:
        counts_q = counts_q.where(LeagueReaction.target_user_id == target_user_id)
    counts_q = counts_q.group_by(LeagueReaction.kind)
    counts = {kind: int(count) for kind, count in (await db.execute(counts_q)).all()}

    mine_q = select(LeagueReaction.kind).where(
        LeagueReaction.league_id == league_id,
        LeagueReaction.from_user_id == user.id,
    )
    if target_user_id is not None:
        mine_q = mine_q.where(LeagueReaction.target_user_id == target_user_id)
    mine = set((await db.scalars(mine_q)).all())

    response = []
    for item in rows:
        source = by_user.get(item.from_user_id)
        target = by_user.get(item.target_user_id)
        response.append({
            "id": item.id,
            "kind": item.kind,
            "created_at": item.created_at,
            "from": {
                "user_id": item.from_user_id,
                "display_name": source.display_name if source else "Участник",
                "avatar_url": source.avatar_url if source else None,
            },
            "target": {
                "user_id": item.target_user_id,
                "display_name": target.display_name if target else "Участник",
                "avatar_url": target.avatar_url if target else None,
            },
        })
    return {"league_id": league_id, "target_user_id": target_user_id, "counts": counts, "mine": sorted(mine), "response": response}


@router.post("/{league_id}/reactions")
async def toggle_reaction(
    league_id: int,
    body: ReactionBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _membership(league_id, user, db)
    kind = body.kind.strip().lower()
    if kind not in REACTION_KINDS:
        raise HTTPException(422, "Неизвестная реакция")
    if body.target_user_id == user.id:
        raise HTTPException(422, "Себя подколоть можно и без приложения")
    await _target_member(league_id, body.target_user_id, db)

    existing = await db.scalar(select(LeagueReaction).where(
        LeagueReaction.league_id == league_id,
        LeagueReaction.from_user_id == user.id,
        LeagueReaction.target_user_id == body.target_user_id,
        LeagueReaction.kind == kind,
    ))
    if existing is not None:
        await db.delete(existing)
        await db.commit()
        return {"ok": True, "active": False, "kind": kind}

    db.add(LeagueReaction(
        league_id=league_id,
        from_user_id=user.id,
        target_user_id=body.target_user_id,
        kind=kind,
        created_at=datetime.now(timezone.utc),
    ))
    await db.commit()
    return {"ok": True, "active": True, "kind": kind}


@router.delete("/{league_id}/reactions/mine")
async def clear_my_reactions(
    league_id: int,
    target_user_id: int | None = Query(default=None, ge=1),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _membership(league_id, user, db)
    q = delete(LeagueReaction).where(
        LeagueReaction.league_id == league_id,
        LeagueReaction.from_user_id == user.id,
    )
    if target_user_id is not None:
        q = q.where(LeagueReaction.target_user_id == target_user_id)
    await db.execute(q)
    await db.commit()
    return {"ok": True}
