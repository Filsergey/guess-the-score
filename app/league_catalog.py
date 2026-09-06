from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import LeagueMember, Tournament, User, UserLeague
from app.services.competition_prepare import prepare_sstats_competition

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
TOURNAMENT_LOGO_IDS = set(ALLOWED_TOURNAMENTS)


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
    """Same-origin proxy for tournament badges so Telegram WebView never loads the CDN directly."""
    if provider_id not in TOURNAMENT_LOGO_IDS:
        raise HTTPException(404, "Tournament logo not configured")
    url = f"https://media.api-sports.io/football/leagues/{provider_id}.png"
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            upstream = await client.get(url, headers={"User-Agent": "guess-the-score/1.0"})
            upstream.raise_for_status()
    except Exception as exc:
        raise HTTPException(502, f"Tournament logo unavailable: {type(exc).__name__}") from exc
    content_type = upstream.headers.get("content-type") or "image/png"
    return Response(
        content=upstream.content,
        media_type=content_type.split(";", 1)[0],
        headers={"Cache-Control": "public, max-age=86400, stale-while-revalidate=604800"},
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
        "source": "fixed-top-tournaments",
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

    # Deliberately blocking: the user league is created only after matches, teams,
    # team logos and players for the selected season are fully prepared.
    try:
        result = await prepare_sstats_competition(
            db,
            body.league_id,
            body.year,
            configured["name"],
        )
    except Exception as exc:
        await db.rollback()
        message = str(exc).strip() or type(exc).__name__
        if len(message) > 500:
            message = message[:497] + "..."
        raise HTTPException(
            502,
            f"Турнир пока не готов: {message}. Лига не создана.",
        ) from exc

    tournament_id = result.get("tournament_id")
    if not tournament_id or result.get("status") != "ready":
        raise HTTPException(502, "Турнир подготовлен не полностью. Лига не создана.")

    tournament = await db.get(Tournament, int(tournament_id))
    if tournament is None:
        raise HTTPException(502, "Турнир исчез после синхронизации. Лига не создана.")
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
