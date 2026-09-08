from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.auth import get_current_user
from app.database import get_db
from app.leagues import _membership
from app.models import Base, LeagueMember, Match, Prediction, Team, User, UserLeague
from app.services.notifications import deliver_to_user

router = APIRouter(prefix="/api/leagues", tags=["league-social"])


class MatchComment(Base):
    __tablename__ = "match_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("user_leagues.id", ondelete="CASCADE"), index=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    from_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    target_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class CommentBody(BaseModel):
    target_user_id: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=180)


class CommentEditBody(BaseModel):
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
        raise HTTPException(409, "Комментарии откроются после начала матча")
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


async def _notify_comment(
    db: AsyncSession,
    target: User,
    actor: User,
    match: Match,
    prediction: Prediction,
    comment_id: int,
    text: str,
) -> None:
    label = await _match_label(match, db)
    score = f"{prediction.home_score}:{prediction.away_score}"
    preview = text if len(text) <= 90 else text[:87].rstrip() + "…"
    body = f"Твой прогноз {score} · {label}.\n{actor.display_name}: «{preview}»."
    await deliver_to_user(
        db,
        target,
        f"social:comment:{comment_id}",
        "participant_activity",
        "Комментарий к прогнозу",
        body,
        f"/?match={match.id}",
        telegram_text=f"Комментарий к прогнозу\n{body}",
    )


def _clean_text(value: str) -> str:
    text = " ".join(value.strip().split())
    if not text:
        raise HTTPException(422, "Напиши хоть что-нибудь")
    return text


async def _own_comment(
    league_id: int,
    match_id: int,
    comment_id: int,
    user: User,
    db: AsyncSession,
) -> MatchComment:
    item = await db.scalar(select(MatchComment).where(
        MatchComment.id == comment_id,
        MatchComment.league_id == league_id,
        MatchComment.match_id == match_id,
    ))
    if item is None:
        raise HTTPException(404, "Комментарий не найден")
    if item.from_user_id != user.id:
        raise HTTPException(403, "Можно изменять только свои комментарии")
    return item


@router.get("/{league_id}/matches/{match_id}/comments")
async def match_comments(
    league_id: int,
    match_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _membership(league_id, user, db)
    await _started_match(league_id, match_id, db)
    comments = (await db.scalars(select(MatchComment).where(
        MatchComment.league_id == league_id,
        MatchComment.match_id == match_id,
    ).order_by(MatchComment.created_at.desc()).limit(100))).all()
    author_ids = {item.from_user_id for item in comments}
    authors = (await db.scalars(select(User).where(User.id.in_(author_ids)))).all() if author_ids else []
    by_author = {item.id: item for item in authors}
    targets: dict[str, dict] = {}
    for item in comments:
        target = targets.setdefault(str(item.target_user_id), {"comments": []})
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
    return {"league_id": league_id, "match_id": match_id, "targets": targets}


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
    text = _clean_text(body.text)
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
    await _notify_comment(db, target, user, match, prediction, item.id, text)
    return {"ok": True, "comment": {"id": item.id, "text": item.text, "created_at": item.created_at}}


@router.put("/{league_id}/matches/{match_id}/comments/{comment_id}")
async def edit_match_comment(
    league_id: int,
    match_id: int,
    comment_id: int,
    body: CommentEditBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _membership(league_id, user, db)
    await _started_match(league_id, match_id, db)
    item = await _own_comment(league_id, match_id, comment_id, user, db)
    item.text = _clean_text(body.text)
    await db.commit()
    await db.refresh(item)
    return {"ok": True, "comment": {"id": item.id, "text": item.text, "created_at": item.created_at}}


@router.delete("/{league_id}/matches/{match_id}/comments/{comment_id}")
async def delete_match_comment(
    league_id: int,
    match_id: int,
    comment_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _membership(league_id, user, db)
    await _started_match(league_id, match_id, db)
    item = await _own_comment(league_id, match_id, comment_id, user, db)
    await db.delete(item)
    await db.commit()
    return {"ok": True}
