from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.auth import router as auth_router
from app.competitions.champions_league import classify_ucl_round
from app.config import get_settings
from app.database import engine, get_db
from app.migrations import migrate_provider_keys
from app.models import Base, Match, Team
from app.predictions import router as predictions_router
from app.providers.api_football import APIFootballProvider
from app.providers.sstats import SStatsProvider
from app.services.football_sync import sync_champions_league
from app.services.sstats_sync import sync_sstats_champions_league, sync_sstats_team_metadata

settings = get_settings()
STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await migrate_provider_keys(conn)
    yield


app = FastAPI(title=settings.app_name, version="0.8.0", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(predictions_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def mini_app() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


def require_admin_token(x_admin_token: str | None) -> None:
    if not settings.admin_sync_token:
        raise HTTPException(status_code=503, detail="ADMIN_SYNC_TOKEN is not configured")
    if x_admin_token != settings.admin_sync_token:
        raise HTTPException(status_code=401, detail="Invalid admin token")


def serialize_match(match: Match, home_team: Team, away_team: Team) -> dict:
    classified = classify_ucl_round(match.season, match.kickoff_at) if match.provider == "sstats" else None
    round_name = match.round_name or (classified["round_label"] if classified else None)
    return {"id": match.id, "provider": match.provider, "provider_id": match.provider_id, "season": match.season,
            "round": round_name, "kickoff_at": match.kickoff_at, "status": match.status_short,
            "status_source": match.status_long, "elapsed": match.elapsed,
            "home": {"id": home_team.id, "provider": home_team.provider, "provider_id": home_team.provider_id,
                     "name": home_team.name, "code": home_team.code, "logo": home_team.logo_url, "goals": match.home_goals},
            "away": {"id": away_team.id, "provider": away_team.provider, "provider_id": away_team.provider_id,
                     "name": away_team.name, "code": away_team.code, "logo": away_team.logo_url, "goals": match.away_goals}}


def _first_item(payload: dict) -> dict:
    data = payload.get("data") or payload.get("response") or []
    if isinstance(data, list): return data[0] if data else {}
    return data if isinstance(data, dict) else {}


def _v(data: dict, name: str):
    camel = name[:1].lower() + name[1:]
    return data.get(camel, data.get(name))


def _merge_non_empty(primary: dict, fallback: dict) -> dict:
    result = dict(fallback)
    for key, value in primary.items():
        if value is not None: result[key] = value
    return result


def serialize_sstats_details(data: dict, glicko: dict | None = None) -> dict:
    stat_names = ["ShotsOnGoal", "ShotsOffGoal", "TotalShots", "BlockedShots", "ShotsInsideBox", "ShotsOutsideBox",
                  "Fouls", "CornerKicks", "BallPossession", "YellowCards", "RedCards", "GoalkeeperSaves",
                  "TotalPasses", "PassesAccurate", "Offsides", "ExpectedGoals", "CalculatedXg"]
    statistics = {name: {"home": _v(data, name + "Home"), "away": _v(data, name + "Away")} for name in stat_names}
    glicko = glicko or {}
    return {"flash_id": _v(data, "FlashId"), "season_uid": _v(data, "SeasonUid"),
            "venue": {"id": _v(data, "VenueId"), "name": _v(data, "VenueName"), "city": _v(data, "VenueCity"), "address": _v(data, "VenueAddress")},
            "coaches": {"home": _v(data, "HomeTeamCoachName"), "away": _v(data, "AwayTeamCoachName")},
            "score": {"ht": {"home": _v(data, "ScoreHomeHT"), "away": _v(data, "ScoreAwayHT")},
                      "ft": {"home": _v(data, "ScoreHomeFT"), "away": _v(data, "ScoreAwayFT")},
                      "et": {"home": _v(data, "ScoreHomeET"), "away": _v(data, "ScoreAwayET")},
                      "penalties": {"home": _v(data, "ScoreHomePT"), "away": _v(data, "ScoreAwayPT")}},
            "odds": {"home": _v(data, "Winner1"), "draw": _v(data, "WinnerX"), "away": _v(data, "Winner2")},
            "model": {"rating": {"home": _v(data, "GlickoRatingHome") or _v(glicko, "RatingHome"), "away": _v(data, "GlickoRatingAway") or _v(glicko, "RatingAway")},
                      "win_probability": {"home": _v(data, "GlickoWinProbHome") or _v(glicko, "WinProbHome"), "away": _v(data, "GlickoWinProbAway") or _v(glicko, "WinProbAway")},
                      "xg": {"home": _v(data, "GlickoXgHome") or _v(glicko, "XgHome"), "away": _v(data, "GlickoXgAway") or _v(glicko, "XgAway")},
                      "odds_xg": {"home": _v(data, "OddsXgHome"), "away": _v(data, "OddsXgAway")}},
            "statistics": statistics,
            "coverage": {"players": _v(data, "CoverageSeasonPlayers"), "events": _v(data, "CoverageSeasonEvents"),
                         "lineups": _v(data, "CoverageSeasonLineups"), "fixture_statistics": _v(data, "CoverageSeasonStatisticsFixtures"),
                         "player_statistics": _v(data, "CoverageSeasonStatisticsPlayers"), "standings": _v(data, "CoverageSeasonStandings"), "odds": _v(data, "CoverageSeasonOdds")}}


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
    if match.provider != "sstats": return {**base, "details_available": False, "details_source": None, "details": None}
    provider = SStatsProvider(); query_data = {}; game_data = {}; glicko_data = {}; errors = []
    try: query_data = _first_item(await provider.query_game_details(match.provider_id))
    except Exception as exc: errors.append(f"query:{type(exc).__name__}")
    if not query_data:
        try: game_data = _first_item(await provider.get_game(match.provider_id))
        except Exception as exc: errors.append(f"game:{type(exc).__name__}")
    try: glicko_data = _first_item(await provider.get_glicko(match.provider_id))
    except Exception as exc: errors.append(f"glicko:{type(exc).__name__}")
    data = _merge_non_empty(query_data, game_data) if (query_data or game_data) else {}
    if not data and not glicko_data: return {**base, "details_available": False, "details_source": None, "details_errors": errors, "details": None}
    details_source = "games/query" if query_data else "games/{id}"
    if glicko_data: details_source += "+glicko"
    return {**base, "details_available": True, "details_source": details_source, "details_errors": errors, "details": serialize_sstats_details(data, glicko_data)}
