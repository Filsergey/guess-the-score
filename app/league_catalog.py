from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import LeagueMember, Tournament, User, UserLeague
from app.services.competition_readiness import prepare_sstats_competition_tolerant
from app.tournament_logos import local_tournament_logo_path

router = APIRouter(prefix="/api/leagues", tags=["league-catalog"])

TOP_TOURNAMENTS = (
    {"league_id": 2, "name": "UEFA Champions League", "country": "Europe"},
    {"league_id": 39, "name": "Premier League", "country": "England"},
    {"league_id": 140, "name": "La Liga", "country": "Spain"},
    {"league_id": 78, "name": "Bundesliga", "country": "Germany"},
    {"league_id": 135, "name": "Serie A", "country": "Italy"},
    {"league_id": 61, "name": "Ligue 1", "country": "France"},
    {"league_id": 88, "name": "Eredivisie", "country": "Netherlands"},
    {"league_id": 71, "name": "Serie A", "country": "Brazil"},
    {"league_id": 94, "name": "Primeira Liga", "country": "Portugal"},
    {"league_id": 262, "name": "Liga MX", "country": "Mexico"},
    {"league_id": 235, "name": "Russian Premier League", "country": "Russia"},
)
ALLOWED_TOURNAMENTS = {item["league_id"]: item for item in TOP_TOURNAMENTS}


class CatalogSyncBody(BaseModel):
    league_id: int = Field(ge=1)
    year: int = Field(ge=2020, le=2100)
    league_name: str | None = Field(default=None, max_length=200)


class LeagueThemeBody(BaseModel):
    icon: str | None = Field(default=None, max_length=900000)
    background: str | None = Field(default=None, max_length=1800000)
    tournament_background: str | None = Field(default=None, max_length=1200000)


def _catalog_seasons() -> list[dict]:
    now = datetime.now(timezone.utc)
    current = now.year if now.month >= 7 else now.year - 1
    return [{"year": year, "uid": None} for year in range(current, 2019, -1)]


def _upstream_error_message(exc: Exception) -> str:
    base = str(exc).strip() or type(exc).__name__
    current = exc
    seen = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, httpx.HTTPStatusError):
            status = current.response.status_code
            reason = current.response.reason_phrase or "HTTP error"
            if status == 429:
                return "SStats HTTP 429 Too Many Requests"
            return f"SStats HTTP {status} {reason}"
        current = current.__cause__ or current.__context__
    return base


async def _theme_league(league_id: int, user: User, db: AsyncSession) -> UserLeague:
    league = await db.get(UserLeague, league_id)
    if league is None:
        raise HTTPException(404, "League not found")
    if user.role != "superadmin":
        member = await db.scalar(
            select(LeagueMember.id).where(
                LeagueMember.league_id == league_id,
                LeagueMember.user_id == user.id,
            )
        )
        if member is None:
            raise HTTPException(403, "You are not a member of this league")
    return league


def _theme_response(league: UserLeague) -> dict:
    return {
        "league_id": league.id,
        "icon": league.theme_icon,
        "background": league.theme_background,
        "tournament_background": league.theme_tournament_background,
    }


@router.get("/tournament-logo/{provider_id}")
async def tournament_logo(provider_id: int):
    """Serve the bundled tournament badge without an upstream request."""
    path = local_tournament_logo_path(provider_id)
    if path is None:
        raise HTTPException(404, "Tournament logo not configured")
    return FileResponse(
        path,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get("/catalog")
async def tournament_catalog(user: User = Depends(get_current_user)):
    del user
    seasons = _catalog_seasons()
    response = [
        {
            **item,
            "logo_url": f"/api/leagues/tournament-logo/{item['league_id']}",
            "seasons": [dict(season) for season in seasons],
        }
        for item in TOP_TOURNAMENTS
    ]
    return {"count": len(response), "response": response, "source": "fixed-top-tournaments"}


@router.get("/catalog/logo-check")
async def tournament_logo_check():
    return {
        "source": "local",
        "count": len(TOP_TOURNAMENTS),
        "matches": [
            {
                "league_id": item["league_id"],
                "name": item["name"],
                "country": item["country"],
                "logo_url": f"/api/leagues/tournament-logo/{item['league_id']}",
            }
            for item in TOP_TOURNAMENTS
        ],
    }


@router.post("/catalog/sync")
async def sync_catalog_tournament(
    body: CatalogSyncBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    del user
    configured = ALLOWED_TOURNAMENTS.get(body.league_id)
    if configured is None:
        raise HTTPException(422, "Этот турнир недоступен для создания лиги")

    # Wait for the bulk preload: matches, teams, crests and player rosters are all
    # attempted before the user league is created. A tiny residual roster gap
    # (roughly 10%, max two clubs) is allowed and repaired in the background.
    # Missing crests are always non-blocking and are retried through SStats only.
    try:
        result = await prepare_sstats_competition_tolerant(
            db,
            body.league_id,
            body.year,
            configured["name"],
        )
    except Exception as exc:
        await db.rollback()
        message = _upstream_error_message(exc)
        if len(message) > 500:
            message = message[:497] + "..."
        raise HTTPException(502, f"Турнир пока не готов: {message}. Лига не создана.") from exc

    tournament_id = result.get("tournament_id")
    if not tournament_id or result.get("status") != "ready":
        raise HTTPException(502, "Турнир подготовлен не полностью. Лига не создана.")

    tournament = await db.get(Tournament, int(tournament_id))
    if tournament is None:
        raise HTTPException(502, "Турнир не найден после подготовки")
    tournament.name = configured["name"]
    tournament.country = configured["country"]
    tournament.logo_url = f"/api/leagues/tournament-logo/{body.league_id}"
    await db.commit()

    return {
        "tournament_id": int(tournament.id),
        "provider_id": body.league_id,
        "season": body.year,
        "name": tournament.name,
        "ready": True,
        "sync": result,
    }


@router.get("/{league_id}/theme")
async def get_league_theme(
    league_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return _theme_response(await _theme_league(league_id, user, db))


@router.put("/{league_id}/theme")
async def set_league_theme(
    league_id: int,
    body: LeagueThemeBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    league = await _theme_league(league_id, user, db)
    if league.owner_user_id != user.id and user.role != "superadmin":
        raise HTTPException(403, "Only the league owner can change its interface")
    league.theme_icon = body.icon or None
    league.theme_background = body.background or None
    league.theme_tournament_background = body.tournament_background or None
    await db.commit()
    return _theme_response(league)


from app.test_fixture import router as test_fixture_router
router.include_router(test_fixture_router)
