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


app = FastAPI(title=settings.app_name, version="0.6.0", lifespan=lifespan)


def require_admin_token(x_admin_token: str | None) -> None:
    if not settings.admin_sync_token:
        raise HTTPException(status_code=503, detail="ADMIN_SYNC_TOKEN is not configured")
    if x_admin_token != settings.admin_sync_token:
        raise HTTPException(status_code=401, detail="Invalid admin token")


def serialize_match(match: Match, home_team: Team, away_team: Team) -> dict:
    return {
        "id": match.id, "provider": match.provider, "provider_id": match.provider_id,
        "season": match.season, "round": match.round_name, "kickoff_at": match.kickoff_at,
        "status": match.status_short, "status_source": match.status_long, "elapsed": match.elapsed,
        "home": {"id": home_team.id, "provider": home_team.provider, "provider_id": home_team.provider_id,
                 "name": home_team.name, "code": home_team.code, "logo": home_team.logo_url, "goals": match.home_goals},
        "away": {"id": away_team.id, "provider": away_team.provider, "provider_id": away_team.provider_id,
                 "name": away_team.name, "code": away_team.code, "logo": away_team.logo_url, "goals": match.away_goals},
    }


def _first_item(payload: dict) -> dict:
    data = payload.get("data") or payload.get("response") or []
    if isinstance(data, list):
        return data[0] if data else {}
    return data if isinstance(data, dict) else {}


def _v(data: dict, name: str):
    camel = name[:1].lower() + name[1:]
    return data.get(camel, data.get(name))


def serialize_sstats_details(data: dict) -> dict:
    stat_names = ["ShotsOnGoal", "ShotsOffGoal", "TotalShots", "BlockedShots", "ShotsInsideBox",
                  "ShotsOutsideBox", "Fouls", "CornerKicks", "BallPossession", "YellowCards", "RedCards",
                  "GoalkeeperSaves", "TotalPasses", "PassesAccurate", "Offsides", "ExpectedGoals", "CalculatedXg"]
    statistics = {name: {"home": _v(data, name + "Home"), "away": _v(data, name + "Away")} for name in stat_names}
    return {
        "flash_id": _v(data, "FlashId"), "season_uid": _v(data, "SeasonUid"),
        "venue": {"id": _v(data, "VenueId"), "name": _v(data, "VenueName"), "city": _v(data, "VenueCity"), "address": _v(data, "VenueAddress")},
        "coaches": {"home": _v(data, "HomeTeamCoachName"), "away": _v(data, "AwayTeamCoachName")},
        "score": {"ht": {"home": _v(data, "ScoreHomeHT"), "away": _v(data, "ScoreAwayHT")},
                  "ft": {"home": _v(data, "ScoreHomeFT"), "away": _v(data, "ScoreAwayFT")},
                  "et": {"home": _v(data, "ScoreHomeET"), "away": _v(data, "ScoreAwayET")},
                  "penalties": {"home": _v(data, "ScoreHomePT"), "away": _v(data, "ScoreAwayPT")}},
        "odds": {"home": _v(data, "Winner1"), "draw": _v(data, "WinnerX"), "away": _v(data, "Winner2")},
        "model": {"rating": {"home": _v(data, "GlickoRatingHome"), "away": _v(data, "GlickoRatingAway")},
                  "win_probability": {"home": _v(data, "GlickoWinProbHome"), "away": _v(data, "GlickoWinProbAway")},
                  "xg": {"home": _v(data, "GlickoXgHome"), "away": _v(data, "GlickoXgAway")},
                  "odds_xg": {"home": _v(data, "OddsXgHome"), "away": _v(data, "OddsXgAway")}},
        "statistics": statistics,
        "coverage": {"players": _v(data, "CoverageSeasonPlayers"), "events": _v(data, "CoverageSeasonEvents"),
                     "lineups": _v(data, "CoverageSeasonLineups"), "fixture_statistics": _v(data, "CoverageSeasonStatisticsFixtures"),
                     "player_statistics": _v(data, "CoverageSeasonStatisticsPlayers"), "standings": _v(data, "CoverageSeasonStandings"),
                     "odds": _v(data, "CoverageSeasonOdds")},
    }


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": settings.app_name, "environment": settings.app_env}


@app.get("/api/admin/football/leagues")
async def football_leagues(x_admin_token: str | None = Header(default=None)) -> dict:
    require_admin_token(x_admin_token)
    try: return await APIFootballProvider().get_leagues()
    except RuntimeError as exc: raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc: raise HTTPException(status_code=502, detail="API-Football request failed") from exc


@app.get("/api/admin/sstats/leagues")
async def sstats_leagues(x_admin_token: str | None = Header(default=None)) -> dict:
    require_admin_token(x_admin_token)
    try: return await SStatsProvider().get_leagues()
    except RuntimeError as exc: raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc: raise HTTPException(status_code=502, detail="SStats request failed") from exc


@app.get("/api/admin/sstats/games")
async def sstats_games(league_id: int = Query(default=2, ge=1), year: int = Query(..., ge=2020, le=2100), x_admin_token: str | None = Header(default=None)) -> dict:
    require_admin_token(x_admin_token)
    try: return await SStatsProvider().get_games(league_id, year)
    except RuntimeError as exc: raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc: raise HTTPException(status_code=502, detail="SStats request failed") from exc


@app.get("/api/admin/sstats/games/{game_id}")
async def sstats_game(game_id: int, x_admin_token: str | None = Header(default=None)) -> dict:
    require_admin_token(x_admin_token)
    try: return await SStatsProvider().get_game(game_id)
    except RuntimeError as exc: raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc: raise HTTPException(status_code=502, detail="SStats game request failed") from exc


@app.get("/api/admin/sstats/teams/{team_id}")
async def sstats_team(team_id: int, x_admin_token: str | None = Header(default=None)) -> dict:
    require_admin_token(x_admin_token)
    try: return await SStatsProvider().get_team(team_id)
    except RuntimeError as exc: raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc: raise HTTPException(status_code=502, detail="SStats team request failed") from exc


@app.post("/api/admin/sync/sstats/champions-league")
async def sync_sstats_champions_league_endpoint(year: int = Query(..., ge=2020, le=2100), x_admin_token: str | None = Header(default=None), db: AsyncSession = Depends(get_db)) -> dict:
    require_admin_token(x_admin_token)
    try: return await sync_sstats_champions_league(db, year)
    except RuntimeError as exc:
        await db.rollback(); raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        await db.rollback(); raise HTTPException(status_code=502, detail=f"SStats Champions League sync failed: {type(exc).__name__}") from exc


@app.post("/api/admin/sync/sstats/team-metadata")
async def sync_sstats_team_metadata_endpoint(limit: int = Query(default=20, ge=1, le=25), x_admin_token: str | None = Header(default=None), db: AsyncSession = Depends(get_db)) -> dict:
    require_admin_token(x_admin_token)
    try: return await sync_sstats_team_metadata(db, limit)
    except Exception as exc:
        await db.rollback(); raise HTTPException(status_code=502, detail=f"SStats team metadata sync failed: {type(exc).__name__}") from exc


@app.post("/api/admin/sync/champions-league")
async def sync_champions_league_endpoint(season: int = Query(..., ge=2020, le=2100), x_admin_token: str | None = Header(default=None), db: AsyncSession = Depends(get_db)) -> dict:
    require_admin_token(x_admin_token)
    try: return await sync_champions_league(db, season)
    except RuntimeError as exc: raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        await db.rollback(); raise HTTPException(status_code=502, detail="Champions League sync failed") from exc


@app.get("/api/matches")
async def matches(season: int | None = Query(default=None, ge=2020, le=2100), provider: str | None = Query(default=None), status: str | None = Query(default=None), db: AsyncSession = Depends(get_db)) -> dict:
    home, away = aliased(Team), aliased(Team)
    stmt = select(Match, home, away).join(home, Match.home_team_id == home.id).join(away, Match.away_team_id == away.id).order_by(Match.kickoff_at)
    if season is not None: stmt = stmt.where(Match.season == season)
    if provider is not None: stmt = stmt.where(Match.provider == provider)
    if status is not None: stmt = stmt.where(Match.status_short == status.upper())
    rows = (await db.execute(stmt)).all()
    items = [serialize_match(match, home_team, away_team) for match, home_team, away_team in rows]
    return {"count": len(items), "response": items}


async def _match_row(match_id: int, db: AsyncSession):
    home, away = aliased(Team), aliased(Team)
    stmt = select(Match, home, away).join(home, Match.home_team_id == home.id).join(away, Match.away_team_id == away.id).where(Match.id == match_id)
    return (await db.execute(stmt)).first()


@app.get("/api/matches/{match_id}")
async def match_detail(match_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    row = await _match_row(match_id, db)
    if row is None: raise HTTPException(status_code=404, detail="Match not found")
    match, home_team, away_team = row
    return serialize_match(match, home_team, away_team)


@app.get("/api/matches/{match_id}/details")
async def match_rich_detail(match_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    row = await _match_row(match_id, db)
    if row is None: raise HTTPException(status_code=404, detail="Match not found")
    match, home_team, away_team = row
    base = serialize_match(match, home_team, away_team)
    if match.provider != "sstats":
        return {**base, "details": None, "details_available": False}
    try:
        payload = await SStatsProvider().query_game_details(match.provider_id)
        data = _first_item(payload)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SStats match details failed: {type(exc).__name__}") from exc
    return {**base, "details_available": bool(data), "details": serialize_sstats_details(data) if data else None}
