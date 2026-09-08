from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.auth import get_current_user
from app.database import get_db
from app.leagues import _membership
from app.models import Base, LeagueMember, Match, Prediction, Team, User, UserLeague
from app.services.notifications import deliver_to_user

router = APIRouter(prefix="/api/leagues", tags=["league-social"])

MATCH_REACTION_KINDS = {"cool", "laugh", "smile", "fire", "eyes", "lion", "see_no_evil", "hear_no_evil"}
LEGACY_REACTION_KINDS = {"laugh", "fire", "clown", "bold", "oracle", "respect"}


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


class MatchComment(Base):
    __tablename__ = "match_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("user_leagues.id", ondelete="CASCADE"), index=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    from_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    target_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class ReactionBody(BaseModel):
    target_user_id: int = Field(ge=1)
    kind: str = Field(min_length=2, max_length=24)


class CommentBody(BaseModel):
    target_user_id: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=180)


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
        raise HTTPException(409, "Реакции и комментарии откроются после начала матча")
    return league, match


async def _target_prediction(match_id: int, target_user_id: int, db: AsyncSession) -> Prediction:
    prediction = await db.scalar(select(Prediction).where(
        Prediction.match_id == match_id,
        Prediction.user_id == target_user_id,
    ))
    if prediction is None:
        raise HTTPException(409, "У участника нет прогноза на этот матч")
    return prediction


async def _match_label(match: Match, db: AsyncSession) -> str:
    home = await db.get(Team, match.home_team_id)
    away = await db.get(Team, match.away_team_id)
    return f"{home.name if home else 'Хозяева'} — {away.name if away else 'Гости'}"


async def _notify_social(
    db: AsyncSession,
    target: User,
    actor: User,
    match: Match,
    prediction: Prediction,
    event_key: str,
    title: str,
    action_text: str,
) -> None:
    label = await _match_label(match, db)
    score = f"{prediction.home_score}:{prediction.away_score}"
    body = f"Твой прогноз {score} · {label}.\n{actor.display_name} {action_text}."
    await deliver_to_user(
        db,
        target,
        event_key,
        "participant_activity",
        title,
        body,
        f"/?match={match.id}",
        telegram_text=f"{title}\n{body}",
    )


@router.get("/{league_id}/matches/{match_id}/reactions")
async def match_reactions(
    league_id: int,
    match_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _membership(league_id, user, db)
    await _started_match(league_id, match_id, db)
    reactions = (await db.scalars(select(MatchReaction).where(
        MatchReaction.league_id == league_id,
        MatchReaction.match_id == match_id,
    ).order_by(MatchReaction.created_at.desc()))).all()
    comments = (await db.scalars(select(MatchComment).where(
        MatchComment.league_id == league_id,
        MatchComment.match_id == match_id,
    ).order_by(MatchComment.created_at.desc()).limit(100))).all()
    author_ids = {item.from_user_id for item in comments}
    authors = (await db.scalars(select(User).where(User.id.in_(author_ids)))).all() if author_ids else []
    by_author = {item.id: item for item in authors}
    targets: dict[str, dict] = {}
    for item in reactions:
        target = targets.setdefault(str(item.target_user_id), {"counts": {}, "mine": [], "comments": []})
        target["counts"][item.kind] = int(target["counts"].get(item.kind, 0)) + 1
        if item.from_user_id == user.id:
            target["mine"].append(item.kind)
    for item in comments:
        target = targets.setdefault(str(item.target_user_id), {"counts": {}, "mine": [], "comments": []})
        author = by_author.get(item.from_user_id)
        if len(target["comments"]) < 5:
            target["comments"].append({
                "id": item.id,
                "text": item.text,
                "created_at": item.created_at,
                "from": {
                    "user_id": item.from_user_id,
                    "display_name": author.display_name if author else "Участник",
                    "avatar_url": author.avatar_url if author else None,
                    "is_mine": item.from_user_id == user.id,
                },
            })
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
    _, match = await _started_match(league_id, match_id, db)
    kind = body.kind.strip().lower()
    if kind not in MATCH_REACTION_KINDS:
        raise HTTPException(422, "Неизвестная реакция")
    if body.target_user_id == user.id:
        raise HTTPException(422, "На свой прогноз реагировать нельзя")
    target = await _target_member(league_id, body.target_user_id, db)
    prediction = await _target_prediction(match_id, body.target_user_id, db)
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
    item = MatchReaction(
        league_id=league_id,
        match_id=match_id,
        from_user_id=user.id,
        target_user_id=body.target_user_id,
        kind=kind,
        created_at=datetime.now(timezone.utc),
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    emoji = {
        "cool": "😎", "laugh": "😂", "smile": "😁", "fire": "🔥",
        "eyes": "👀", "lion": "🦁", "see_no_evil": "🙈", "hear_no_evil": "🙉",
    }[kind]
    await _notify_social(
        db, target, user, match, prediction,
        f"social:reaction:{item.id}",
        "Реакция на прогноз",
        f"поставил {emoji}",
    )
    return {"ok": True, "active": True, "kind": kind}


@router.post("/{league_id}/matches/{match_id}/comments")
async def add_match_comment(
    league_id: int,
    match_id: int,
    body: CommentBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _membership(league_id, user, db)
    _, match = await _started_match(league_id, match_id, db)
    if body.target_user_id == user.id:
        raise HTTPException(422, "Свой прогноз можно обсудить и с собой")
    target = await _target_member(league_id, body.target_user_id, db)
    prediction = await _target_prediction(match_id, body.target_user_id, db)
    text = " ".join(body.text.strip().split())
    if not text:
        raise HTTPException(422, "Напиши хоть что-нибудь")
    item = MatchComment(
        league_id=league_id,
        match_id=match_id,
        from_user_id=user.id,
        target_user_id=body.target_user_id,
        text=text,
        created_at=datetime.now(timezone.utc),
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    preview = text if len(text) <= 90 else text[:87].rstrip() + "…"
    await _notify_social(
        db, target, user, match, prediction,
        f"social:comment:{item.id}",
        "Комментарий к прогнозу",
        f"написал: «{preview}»",
    )
    return {"ok": True, "comment": {"id": item.id, "text": item.text, "created_at": item.created_at}}


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
    if kind not in LEGACY_REACTION_KINDS:
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
