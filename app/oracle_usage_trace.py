from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Boolean, DateTime, Integer, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

import app.oracle as oracle
from app.auth import get_current_user
from app.database import SessionLocal, get_db
from app.models import Base, Match, Team, User
from app.openai_usage import _require_admin

logger = logging.getLogger(__name__)
_ORIGIN: ContextVar[str] = ContextVar("gts_oracle_origin", default="user")
_INSTALLED = False


class OracleActivityEvent(Base):
    __tablename__ = "oracle_activity_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(24), index=True)  # cache_hit | initial | delta
    origin: Mapped[str] = mapped_column(String(24), index=True)  # user | auto_t72 | admin
    status: Mapped[str] = mapped_column(String(20), default="success", index=True)
    openai_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    changes_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )


def _short(value, limit: int = 52) -> str:
    if value is None:
        return "∅"
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    else:
        text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _change_lines(value, prefix: str = "", out: list[str] | None = None, limit: int = 8) -> list[str]:
    """Turn a recursive context diff into a few readable leaf changes."""
    out = out if out is not None else []
    if len(out) >= limit:
        return out
    if not isinstance(value, dict):
        if prefix:
            out.append(f"{prefix}: {_short(value)}")
        return out

    if "before" in value or "after" in value or value.get("removed") is True:
        before = _short(value.get("before")) if "before" in value else "∅"
        after = "удалено" if value.get("removed") is True else _short(value.get("after"))
        out.append(f"{prefix}: {before} → {after}" if prefix else f"{before} → {after}")
        return out

    for key, child in value.items():
        if len(out) >= limit:
            break
        path = f"{prefix}.{key}" if prefix else str(key)
        _change_lines(child, path, out, limit)
    return out


async def _persist_activity(events: list[dict]) -> None:
    if not events:
        return
    try:
        async with SessionLocal() as db:
            for event in events:
                db.add(
                    OracleActivityEvent(
                        match_id=int(event["match_id"]),
                        action=str(event["action"]),
                        origin=str(event.get("origin") or "user"),
                        status=str(event.get("status") or "success"),
                        openai_requested=bool(event.get("openai_requested")),
                        changes_json=json.dumps(event.get("changes") or [], ensure_ascii=False),
                    )
                )
            await db.commit()
    except Exception:
        # Telemetry must never prevent a forecast from being returned.
        logger.exception("Failed to persist Oracle activity trace")


def install_oracle_usage_trace() -> None:
    """Trace why Oracle used OpenAI, including zero-cost cache hits.

    The trace wraps the already-installed Structured Outputs analyzer, so it does
    not change prediction prompts or model behavior. Event-driven T-72h generation
    receives a separate origin label; direct /matches/{id} calls remain `user`.
    """
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original_refresh = oracle._refresh_one_context
    original_ai = oracle._ai_analyze_batch
    original_generate = oracle.generate_or_refresh_matches

    async def traced_refresh(db, match, force=False):
        result = await original_refresh(db, match, force=force)
        if result.get("status") == "cache-unchanged":
            await _persist_activity(
                [
                    {
                        "match_id": match.id,
                        "action": "cache_hit",
                        "origin": _ORIGIN.get(),
                        "status": "success",
                        "openai_requested": False,
                    }
                ]
            )
        return result

    async def traced_ai(items):
        result = await original_ai(items)
        origin = _ORIGIN.get()
        events = []
        for item in items:
            match_id = int(item["ctx"]["match"].id)
            mode = str(item.get("mode") or "initial")
            events.append(
                {
                    "match_id": match_id,
                    "action": mode,
                    "origin": origin,
                    "status": "success" if match_id in result else "error",
                    "openai_requested": True,
                    "changes": _change_lines(item.get("changes") or {}) if mode == "delta" else [],
                }
            )
        await _persist_activity(events)
        return result

    async def traced_generate(db, matches, *args, origin: str | None = None, **kwargs):
        token = _ORIGIN.set(origin or "admin")
        try:
            return await original_generate(db, matches, *args, **kwargs)
        finally:
            _ORIGIN.reset(token)

    oracle._refresh_one_context = traced_refresh
    oracle._ai_analyze_batch = traced_ai
    oracle.generate_or_refresh_matches = traced_generate

    # oracle_events imported generate_or_refresh_matches by value. Replace its
    # local reference so automatic one-shot T-72h INITIALs are labelled correctly.
    try:
        from app.services import oracle_events

        async def auto_generate(db, matches, *args, **kwargs):
            return await traced_generate(db, matches, *args, origin="auto_t72", **kwargs)

        oracle_events.generate_or_refresh_matches = auto_generate
    except Exception:
        logger.exception("Could not attach Oracle auto-generation trace")


activity_router = APIRouter(prefix="/admin/openai", tags=["admin-openai"])


@activity_router.get("/activity")
async def admin_oracle_activity(
    days: int = Query(default=30, ge=1, le=90),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _require_admin(user)
    start = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        await db.execute(
            select(OracleActivityEvent)
            .where(OracleActivityEvent.created_at >= start)
            .order_by(OracleActivityEvent.created_at.desc())
            .limit(120)
        )
    ).scalars().all()

    match_ids = {row.match_id for row in rows}
    matches = (
        (await db.execute(select(Match).where(Match.id.in_(match_ids)))).scalars().all()
        if match_ids
        else []
    )
    by_match = {match.id: match for match in matches}
    team_ids = {m.home_team_id for m in matches} | {m.away_team_id for m in matches}
    teams = (
        (await db.execute(select(Team).where(Team.id.in_(team_ids)))).scalars().all()
        if team_ids
        else []
    )
    team_names = {team.id: team.name for team in teams}

    def label(match_id: int) -> tuple[str, datetime | None]:
        match = by_match.get(match_id)
        if not match:
            return f"Матч #{match_id}", None
        return (
            f"{team_names.get(match.home_team_id, 'Хозяева')} — {team_names.get(match.away_team_id, 'Гости')}",
            match.kickoff_at,
        )

    recent = []
    for row in rows[:60]:
        match_name, kickoff_at = label(row.match_id)
        try:
            changes = json.loads(row.changes_json or "[]")
        except Exception:
            changes = []
        recent.append(
            {
                "created_at": row.created_at,
                "match_id": row.match_id,
                "match": match_name,
                "kickoff_at": kickoff_at,
                "action": row.action,
                "origin": row.origin,
                "status": row.status,
                "openai_requested": row.openai_requested,
                "changes": changes if isinstance(changes, list) else [],
            }
        )

    return {
        "period_days": days,
        "summary": {
            "cache_hits": sum(1 for row in rows if row.action == "cache_hit"),
            "initial": sum(1 for row in rows if row.action == "initial"),
            "delta": sum(1 for row in rows if row.action == "delta"),
            "auto_initial": sum(1 for row in rows if row.action == "initial" and row.origin == "auto_t72"),
            "user_initial": sum(1 for row in rows if row.action == "initial" and row.origin == "user"),
            "user_delta": sum(1 for row in rows if row.action == "delta" and row.origin == "user"),
            "openai_requests": sum(1 for row in rows if row.openai_requested),
            "errors": sum(1 for row in rows if row.status != "success"),
        },
        "recent": recent,
    }
