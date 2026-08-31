from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.config import get_settings
from app.database import engine, get_db
from app.migrations import migrate_provider_keys
from app.models import Base, Match, Team
from app.providers.api_football import APIFootballProvider
from app.providers.sstats import SStatsProvider
from app.services.football_sync import sync_champions_league
from app.services.sstats_sync import sync_sstats_champions_league, sync_sstats_team_metadata

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await migrate_provider_keys(conn)
    yield


app = FastAPI(title=settings.app_name, version="0.5.0", lifespan=lifespan)


def require_admin_token(x_admin_token: str | None) -> None:
    if not settings.admin_sync_token:
        raise HTTPException(status_code=503, detail="ADMIN_SYNC_TOKEN is not configured")
    if x_admin_token != settings.admin_sync_token:
        raise HTTPException(status_code=401, detail="Invalid admin token")


def serialize_match(match: Match, home_team: Team, away_team: Team) -> dict:
    return {
        "id": match.id,
        "provider": match.provider,
        "provider_id": match.provider_id,
        "season": match.season,
        "round": match.round_name,
        "kickoff_at": match.kickoff_at,
        "status": match.status_short,
        "status_source": match.status_long,
        "elapsed": match.elapsed,
        "home": {
            "id": home_team.id,
            "provider": home_team.provider,
            "provider_id": home_team.provider_id,
            "name": home_team.name,
            "code": home_team.code,
            "logo": home_team.logo_url,
            "goals": match.home_goals,
        },
        "away": {
            "id": away_team.id,
            "provider": away_team.provider,
            "provider_id": away_team.provider_id,
            "name": away_team.name,
            "code": away_team.code,
            "logo": away_team.logo_url,
            "goals": match.away_goals,
        },
    }


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": settings.app_name, "environment": settings.app_env}


@app.get("/api/admin/football/leagues")
async def football_leagues(x_admin_token: str | None = Header(default=None)) -> dict:
    require_admin_token(x_admin_token)
    try:
        return await APIFootballProvider().get_leagues()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="API-Football request failed") from exc


@app.get("/api/admin/sstats/leagues")
async def sstats_leagues(x_admin_token: str | None = Header(default=None)) -> dict:
    require_admin_token(x_admin_token)
    try:
        return await SStatsProvider().get_leagues()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="SStats request failed") from exc


@app.get("/api/admin/sstats/games")
async def sstats_games(
    league_id: int = Query(default=2, ge=1),
    year: int = Query(..., ge=2020, le=2100),
    x_admin_token: str | None = Header(default=None),
) -> dict:
    require_admin_token(x_admin_token)
    try:
        return await SStatsProvider().get_games(league_id, year)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="SStats request failed") from exc


@app.get("/api/admin/sstats/games/{game_id}")
async def sstats_game(game_id: int, x_admin_token: str | None = Header(default=None)) -> dict:
    require_admin_token(x_admin_token)
    try:
        return await SStatsProvider().get_game(game_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="SStats game request failed") from exc


@app.get("/api/admin/sstats/teams/{team_id}")
async def sstats_team(team_id: int, x_admin_token: str | None = Header(default=None)) -> dict:
    require_admin_token(x_admin_token)
    try:
        return await SStatsProvider().get_team(team_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="SStats team request failed") from exc


@app.post("/api/admin/sync/sstats/champions-league")
async def sync_sstats_champions_league_endpoint(
    year: int = Query(..., ge=2020, le=2100),
    x_admin_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    require_admin_token(x_admin_token)
    try:
        return await sync_sstats_champions_league(db, year)
    except RuntimeError as exc:
        await db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=502, detail=f"SStats Champions League sync failed: {type(exc).__name__}") from exc


@app.post("/api/admin/sync/sstats/team-metadata")
async def sync_sstats_team_metadata_endpoint(
    limit: int = Query(default=20, ge=1, le=25),
    x_admin_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    require_admin_token(x_admin_token)
    try:
        return await sync_sstats_team_metadata(db, limit)
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=502, detail=f"SStats team metadata sync failed: {type(exc).__name__}") from exc


@app.post("/api/admin/sync/champions-league")
async def sync_champions_league_endpoint(
    season: int = Query(..., ge=2020, le=2100),
    x_admin_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Legacy API-Football sync, kept as a fallback/history provider."""
    require_admin_token(x_admin_token)
    try:
        return await sync_champions_league(db, season)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=502, detail="Champions League sync failed") from exc


@app.get("/api/matches")
async def matches(
    season: int | None = Query(default=None, ge=2020, le=2100),
    provider: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    home = aliased(Team)
    away = aliased(Team)

    stmt = (
        select(Match, home, away)
        .join(home, Match.home_team_id == home.id)
        .join(away, Match.away_team_id == away.id)
        .order_by(Match.kickoff_at)
    )
    if season is not None:
        stmt = stmt.where(Match.season == season)
    if provider is not None:
        stmt = stmt.where(Match.provider == provider)
    if status is not None:
        stmt = stmt.where(Match.status_short == status.upper())

    rows = (await db.execute(stmt)).all()
    items = [serialize_match(match, home_team, away_team) for match, home_team, away_team in rows]
    return {"count": len(items), "response": items}


@app.get("/api/matches/{match_id}")
async def match_detail(match_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    home = aliased(Team)
    away = aliased(Team)
    stmt = (
        select(Match, home, away)
        .join(home, Match.home_team_id == home.id)
        .join(away, Match.away_team_id == away.id)
        .where(Match.id == match_id)
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Match not found")
    match, home_team, away_team = row
    return serialize_match(match, home_team, away_team)
