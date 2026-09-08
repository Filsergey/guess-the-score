from __future__ import annotations

import functools
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import BigInteger, DateTime, Integer, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.auth import get_current_user
from app.config import get_settings
from app.database import SessionLocal, get_db
from app.models import Base, User

logger = logging.getLogger(__name__)
settings = get_settings()

# Current production Oracle model. Keep pricing beside the usage snapshot so old
# rows remain understandable if the model is changed later.
MODEL_PRICING = {
    "gpt-5-mini": {"input": 0.25, "cached_input": 0.025, "output": 2.0},
    "gpt-5-mini-2025-08-07": {"input": 0.25, "cached_input": 0.025, "output": 2.0},
}
WEB_SEARCH_USD_PER_CALL = 0.01


class OpenAIUsageEvent(Base):
    __tablename__ = "openai_usage_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_kind: Mapped[str] = mapped_column(String(40), default="other", index=True)
    model: Mapped[str] = mapped_column(String(100), default="unknown", index=True)
    status: Mapped[str] = mapped_column(String(20), default="success", index=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    web_search_calls: Mapped[int] = mapped_column(Integer, default=0)
    initial_items: Mapped[int] = mapped_column(Integer, default=0)
    delta_items: Mapped[int] = mapped_column(Integer, default=0)
    match_count: Mapped[int] = mapped_column(Integer, default=0)
    team_count: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_microusd: Mapped[int] = mapped_column(BigInteger, default=0)
    match_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    team_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


def _value(obj, name, default=0):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _as_int(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _input_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                content = item.get("content")
                if isinstance(content, str):
                    parts.append(content)
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and isinstance(block.get("text"), str):
                            parts.append(block["text"])
        return "\n".join(parts)
    return str(value or "")


def _json_after_marker(text: str, marker: str):
    if marker not in text:
        return None
    raw = text.split(marker, 1)[1].strip()
    try:
        return json.loads(raw)
    except Exception:
        start = raw.find("[")
        end = raw.rfind("]")
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except Exception:
                return None
    return None


def _request_meta(model: str | None, input_value) -> dict:
    text = _input_text(input_value)
    meta = {
        "request_kind": "other",
        "model": str(model or settings.openai_oracle_model or "unknown"),
        "match_ids": [],
        "team_ids": [],
        "initial_items": 0,
        "delta_items": 0,
    }
    news = _json_after_marker(text, "Команды для проверки:")
    if isinstance(news, list):
        meta["request_kind"] = "team_news"
        meta["team_ids"] = [int(x.get("team_id")) for x in news if isinstance(x, dict) and str(x.get("team_id", "")).isdigit()]
        return meta
    analysis = _json_after_marker(text, "Данные для анализа:")
    if isinstance(analysis, list):
        meta["request_kind"] = "oracle_analysis"
        for item in analysis:
            if not isinstance(item, dict):
                continue
            try:
                meta["match_ids"].append(int(item.get("match_id")))
            except (TypeError, ValueError):
                pass
            mode = str(item.get("mode") or "").lower()
            if mode == "initial":
                meta["initial_items"] += 1
            elif mode == "delta":
                meta["delta_items"] += 1
    return meta


def _web_search_count(response) -> int:
    count = 0
    for item in _value(response, "output", []) or []:
        if str(_value(item, "type", "")) == "web_search_call":
            count += 1
    return count


def _usage_from_response(response) -> dict:
    usage = _value(response, "usage", None)
    input_tokens = _as_int(_value(usage, "input_tokens", 0))
    output_tokens = _as_int(_value(usage, "output_tokens", 0))
    total_tokens = _as_int(_value(usage, "total_tokens", input_tokens + output_tokens))
    details = _value(usage, "input_tokens_details", None)
    cached = min(input_tokens, _as_int(_value(details, "cached_tokens", 0)))
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "web_search_calls": _web_search_count(response),
    }


def _estimated_cost_microusd(model: str, usage: dict) -> int:
    price = MODEL_PRICING.get(model)
    token_cost = 0.0
    if price:
        input_tokens = usage["input_tokens"]
        cached = min(input_tokens, usage["cached_input_tokens"])
        uncached = max(0, input_tokens - cached)
        token_cost = (
            uncached * price["input"] / 1_000_000
            + cached * price["cached_input"] / 1_000_000
            + usage["output_tokens"] * price["output"] / 1_000_000
        )
    web_cost = usage["web_search_calls"] * WEB_SEARCH_USD_PER_CALL
    return max(0, round((token_cost + web_cost) * 1_000_000))


async def _persist(meta: dict, *, response=None, error: Exception | None = None) -> None:
    usage = _usage_from_response(response) if response is not None else {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "web_search_calls": 0,
    }
    model = str(meta.get("model") or "unknown")
    try:
        async with SessionLocal() as db:
            db.add(
                OpenAIUsageEvent(
                    request_kind=str(meta.get("request_kind") or "other"),
                    model=model,
                    status="error" if error else "success",
                    input_tokens=usage["input_tokens"],
                    cached_input_tokens=usage["cached_input_tokens"],
                    output_tokens=usage["output_tokens"],
                    total_tokens=usage["total_tokens"],
                    web_search_calls=usage["web_search_calls"],
                    initial_items=_as_int(meta.get("initial_items")),
                    delta_items=_as_int(meta.get("delta_items")),
                    match_count=len(meta.get("match_ids") or []),
                    team_count=len(meta.get("team_ids") or []),
                    estimated_cost_microusd=_estimated_cost_microusd(model, usage),
                    match_ids_json=json.dumps(meta.get("match_ids") or []),
                    team_ids_json=json.dumps(meta.get("team_ids") or []),
                    error_type=type(error).__name__[:100] if error else None,
                )
            )
            await db.commit()
    except Exception:
        # Accounting must never break Oracle generation.
        logger.exception("Failed to persist OpenAI usage event")


def install_openai_usage_tracking() -> None:
    """Wrap Responses API once and persist real token/tool usage for every call."""
    try:
        from openai.resources.responses.responses import AsyncResponses
    except Exception:
        logger.exception("OpenAI usage tracking could not import AsyncResponses")
        return

    current = AsyncResponses.create
    if getattr(current, "_gts_usage_tracking", False):
        return

    @functools.wraps(current)
    async def wrapped(self, *args, **kwargs):
        meta = _request_meta(kwargs.get("model"), kwargs.get("input"))
        try:
            response = await current(self, *args, **kwargs)
        except Exception as exc:
            await _persist(meta, error=exc)
            raise
        await _persist(meta, response=response)
        return response

    wrapped._gts_usage_tracking = True
    AsyncResponses.create = wrapped


def _summary(rows: list[OpenAIUsageEvent]) -> dict:
    input_tokens = sum(x.input_tokens for x in rows)
    cached_tokens = sum(x.cached_input_tokens for x in rows)
    cost_microusd = sum(x.estimated_cost_microusd for x in rows)
    return {
        "api_calls": len(rows),
        "successful_calls": sum(1 for x in rows if x.status == "success"),
        "failed_calls": sum(1 for x in rows if x.status != "success"),
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_tokens,
        "output_tokens": sum(x.output_tokens for x in rows),
        "total_tokens": sum(x.total_tokens for x in rows),
        "cache_percent": round(cached_tokens * 100 / input_tokens, 1) if input_tokens else 0.0,
        "web_search_calls": sum(x.web_search_calls for x in rows),
        "initial_items": sum(x.initial_items for x in rows),
        "delta_items": sum(x.delta_items for x in rows),
        "news_teams": sum(x.team_count for x in rows if x.request_kind == "team_news"),
        "estimated_cost_usd": round(cost_microusd / 1_000_000, 6),
    }


def _require_admin(user: User) -> None:
    if user.role not in {"admin", "superadmin"}:
        raise HTTPException(status_code=403, detail="Admin access required")


admin_router = APIRouter(prefix="/admin/openai", tags=["admin-openai"])


@admin_router.get("/usage")
async def admin_openai_usage(
    days: int = Query(default=30, ge=1, le=90),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _require_admin(user)
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    rows = (
        await db.execute(
            select(OpenAIUsageEvent)
            .where(OpenAIUsageEvent.created_at >= start)
            .order_by(OpenAIUsageEvent.created_at.desc())
        )
    ).scalars().all()

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)
    today_rows = [x for x in rows if x.created_at >= today_start]
    week_rows = [x for x in rows if x.created_at >= week_start]

    daily_map: dict[str, list[OpenAIUsageEvent]] = defaultdict(list)
    kind_map: dict[str, list[OpenAIUsageEvent]] = defaultdict(list)
    for row in rows:
        daily_map[row.created_at.astimezone(timezone.utc).date().isoformat()].append(row)
        kind_map[row.request_kind].append(row)

    daily = [{"date": date, **_summary(items)} for date, items in sorted(daily_map.items())]
    by_kind = [{"kind": kind, **_summary(items)} for kind, items in sorted(kind_map.items())]
    recent = [
        {
            "created_at": row.created_at,
            "kind": row.request_kind,
            "model": row.model,
            "status": row.status,
            "input_tokens": row.input_tokens,
            "cached_input_tokens": row.cached_input_tokens,
            "output_tokens": row.output_tokens,
            "total_tokens": row.total_tokens,
            "web_search_calls": row.web_search_calls,
            "initial_items": row.initial_items,
            "delta_items": row.delta_items,
            "match_count": row.match_count,
            "team_count": row.team_count,
            "estimated_cost_usd": round(row.estimated_cost_microusd / 1_000_000, 6),
            "error_type": row.error_type,
        }
        for row in rows[:40]
    ]
    model = settings.openai_oracle_model
    pricing = MODEL_PRICING.get(model)
    return {
        "tracked_since": rows[-1].created_at if rows else None,
        "period_days": days,
        "model": model,
        "pricing": {
            "known": pricing is not None,
            "input_per_million": pricing["input"] if pricing else None,
            "cached_input_per_million": pricing["cached_input"] if pricing else None,
            "output_per_million": pricing["output"] if pricing else None,
            "web_search_per_call": WEB_SEARCH_USD_PER_CALL,
        },
        "today": _summary(today_rows),
        "last_7_days": _summary(week_rows),
        "period": _summary(rows),
        "daily": daily,
        "by_kind": by_kind,
        "recent": recent,
    }
