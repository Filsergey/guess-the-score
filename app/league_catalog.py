import asyncio
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import SessionLocal, get_db
from app.models import LeagueMember, Tournament, User, UserLeague
from app.services.sstats_sync import sync_sstats_competition

router = APIRouter(prefix="/api/leagues", tags=["league-catalog"])

# Fixed creation catalog. We intentionally do not call SStats /Leagues here:
# that endpoint can be unavailable while Games/list continues to work.
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
    # Enough history for the UI, while keeping the selector compact.
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


async def _sync_competition_in_background(league_id: int, year: int, league_name: str) -> None:
    """Populate matches after league creation without making the user wait for SStats.

    SStats occasionally returns transient HTTP errors. Creation must still succeed, so
    we retry the idempotent sync in a fresh DB session a few times after the response.
    """
    for delay in (0, 4, 15):
        if delay:
            await asyncio.sleep(delay)
        try:
            async with SessionLocal() as session:
                await sync_sstats_competition(session, league_id, year, league_name)
            return
        except Exception:
            # The next retry gets a new SQLAlchemy session and a clean transaction.
            continue


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
    """Read-only diagnostic for the fixed tournament catalog."""
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
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    del user
    configured = ALLOWED_TOURNAMENTS.get(body.league_id)
    if configured is None:
        raise HTTPException(422, "Этот турнир недоступен для создания лиги")

    # Tournament identity is local application data. It must not depend on SStats
    # being online at the exact moment a user presses "Создать лигу".
    tournament = await db.scalar(
        select(Tournament).where(
            Tournament.provider == "sstats",
            Tournament.provider_id == body.league_id,
        )
    )
    if tournament is None:
        tournament = Tournament(
            provider="sstats",
            provider_id=body.league_id,
            name=configured["name"],
            country=configured["country"],
        )
        db.add(tournament)
        await db.flush()
    else:
        tournament.name = configured["name"]
        tournament.country = configured["country"]
    await db.commit()

    # Match import is intentionally deferred. The endpoint now returns immediately,
    # so a temporary SStats 4xx/5xx/timeout can never prevent league creation.
    background_tasks.add_task(
        _sync_competition_in_background,
        body.league_id,
        body.year,
        configured["name"],
    )

    return {
        "tournament_id": int(tournament.id),
        "provider_id": body.league_id,
        "season": body.year,
        "name": tournament.name,
        "sync": {
            "status": "queued",
            "provider": "sstats",
            "league_id": body.league_id,
            "year": body.year,
        },
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