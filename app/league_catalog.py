from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import LeagueMember, Tournament, User, UserLeague
from app.providers.sstats import SStatsProvider
from app.services.sstats_sync import sync_sstats_competition

router = APIRouter(prefix="/api/leagues", tags=["league-catalog"])


class CatalogSyncBody(BaseModel):
    league_id: int = Field(ge=1)
    year: int = Field(ge=2020, le=2100)
    league_name: str | None = Field(default=None, max_length=200)


class LeagueThemeBody(BaseModel):
    icon: str | None = Field(default=None, max_length=900000)
    background: str | None = Field(default=None, max_length=1800000)
    tournament_background: str | None = Field(default=None, max_length=1200000)


def _pick(row: dict, *names, default=None):
    for name in names:
        if name in row:
            return row[name]
    return default


def _country_name(value):
    if isinstance(value, dict):
        return _pick(value, "name", "Name", default=None)
    return value if isinstance(value, str) else None


def _season_rows(row: dict) -> list[dict]:
    raw = []
    for key in ("seasons", "Seasons", "season", "Season"):
        value = row.get(key)
        if isinstance(value, list):
            raw.extend(x for x in value if isinstance(x, dict))
        elif isinstance(value, dict):
            raw.append(value)
    result = []
    seen = set()
    for season in raw:
        year = _pick(season, "year", "Year", "seasonYear", "SeasonYear")
        try:
            year = int(year)
        except (TypeError, ValueError):
            continue
        if year in seen:
            continue
        seen.add(year)
        result.append({
            "year": year,
            "uid": _pick(season, "uid", "Uid", "UID", "seasonUid", "SeasonUid", "id", "Id"),
        })
    result.sort(key=lambda x: x["year"], reverse=True)
    return result


def _catalog_priority(item: dict) -> tuple:
    """Put the five most recognisable club competitions first, then keep the rest alphabetical."""
    name = str(item.get("name") or "").lower().replace("-", " ")
    country = str(item.get("country") or "").lower()
    popular = (
        (0, ("champions league",)),
        (1, ("premier league",)),
        (2, ("la liga", "laliga", "primera division")),
        (3, ("serie a",)),
        (4, ("bundesliga",)),
    )
    for rank, aliases in popular:
        if any(alias in name for alias in aliases):
            # Avoid accidentally prioritising similarly named youth/women/reserve competitions.
            if any(word in name for word in ("women", "woman", "femin", "u19", "u21", "u23", "youth", "reserve")):
                break
            return (0, rank, country, name)
    return (1, 99, country, name)


async def _theme_league(league_id: int, user: User, db: AsyncSession) -> UserLeague:
    league = await db.get(UserLeague, league_id)
    if league is None:
        raise HTTPException(404, "League not found")
    if user.role != "superadmin":
        member = await db.scalar(select(LeagueMember.id).where(LeagueMember.league_id == league_id, LeagueMember.user_id == user.id))
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


@router.get("/catalog")
async def tournament_catalog(user: User = Depends(get_current_user)):
    del user
    try:
        payload = await SStatsProvider().get_leagues()
    except Exception as exc:
        raise HTTPException(502, f"SStats catalog unavailable: {type(exc).__name__}") from exc
    rows = payload.get("data") or payload.get("response") or []
    if isinstance(rows, dict):
        rows = [rows]
    result = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        raw_id = _pick(row, "id", "Id", "leagueId", "LeagueId")
        try:
            league_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        name = str(_pick(row, "name", "Name", "leagueName", "LeagueName", default=f"SStats #{league_id}"))
        seasons = _season_rows(row)
        result.append({
            "league_id": league_id,
            "name": name,
            "country": _country_name(_pick(row, "country", "Country", "countryName", "CountryName")),
            "logo_url": _pick(row, "logoUrl", "LogoUrl", "logo", "Logo"),
            "seasons": seasons,
        })
    result.sort(key=_catalog_priority)
    return {"count": len(result), "response": result}


@router.post("/catalog/sync")
async def sync_catalog_tournament(
    body: CatalogSyncBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    del user
    try:
        result = await sync_sstats_competition(db, body.league_id, body.year, body.league_name)
    except Exception as exc:
        await db.rollback()
        raise HTTPException(502, f"SStats tournament sync failed: {type(exc).__name__}") from exc
    tournament_id = result.get("tournament_id")
    if not tournament_id:
        raise HTTPException(422, "SStats did not return matches for this tournament and season")
    tournament = await db.get(Tournament, int(tournament_id))
    return {
        "tournament_id": int(tournament_id),
        "provider_id": body.league_id,
        "season": body.year,
        "name": tournament.name if tournament else (body.league_name or f"SStats #{body.league_id}"),
        "sync": result,
    }


@router.get("/{league_id}/theme")
async def get_league_theme(league_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    league = await _theme_league(league_id, user, db)
    return _theme_response(league)


@router.put("/{league_id}/theme")
async def set_league_theme(league_id: int, body: LeagueThemeBody, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    league = await _theme_league(league_id, user, db)
    if league.owner_user_id != user.id and user.role != "superadmin":
        raise HTTPException(403, "Only the league owner can change its interface")
    league.theme_icon = body.icon or None
    league.theme_background = body.background or None
    league.theme_tournament_background = body.tournament_background or None
    await db.commit()
    return _theme_response(league)
