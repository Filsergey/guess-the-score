import asyncio
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.leagues import _membership
from app.models import Team, Tournament, User, UserLeague
from app.providers.sstats import SStatsProvider

router = APIRouter(prefix="/api/leagues", tags=["tournament-standings"])
_cache = {}
_lock = asyncio.Lock()


async def standings_payload(tournament_id, season):
    key = (tournament_id, season)
    async with _lock:
        cached = _cache.get(key)
        if cached and monotonic() - cached[0] < 120:
            return cached[1]
        payload = await SStatsProvider().get_standings(league_id=tournament_id, year=season)
        data = payload.get("data") or {}
        if not isinstance(data, dict) or not isinstance(data.get("tables"), list):
            raise ValueError("Invalid standings response")
        if len(_cache) >= 128:
            _cache.pop(next(iter(_cache)))
        _cache[key] = (monotonic(), data)
        return data


def normalize_tables(data, team_map, is_ucl):
    groups = []
    for table in data.get("tables", []):
        rows = table.get("rows") or []
        by_group = {}
        for row in rows:
            by_group.setdefault(row.get("groupName") or "Турнирная таблица", []).append(row)
        for name, items in by_group.items():
            league_phase = is_ucl and str(name).casefold() == "league phase" and len(items) == 36
            output = []
            for row in sorted(items, key=lambda x: x["rank"]):
                tid = row["teamId"]
                team = team_map.get(tid)
                rank = row["rank"]
                gf, ga = row.get("goalsFor"), row.get("goalsAgainst")
                output.append({
                    "rank": rank,
                    "name": team.name if team else row.get("teamName") or f"Клуб №{tid}",
                    "logo": f"/api/team-logo/db/{team.id}" if team else None,
                    "played": row.get("played"), "wins": row.get("wins"),
                    "draws": row.get("draws"), "losses": row.get("loses"),
                    "goals_for": gf, "goals_against": ga,
                    "difference": gf - ga if gf is not None and ga is not None else None,
                    "points": row.get("points"),
                    "zone": ("direct" if rank <= 8 else "playoff" if rank <= 24 else "out") if league_phase else None,
                })
            groups.append({"name": "Общий этап" if league_phase else name,
                           "ucl_zones": league_phase, "rows": output})
    return groups


@router.get("/{league_id}/tournament-standings")
async def tournament_standings(league_id: int, user: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    await _membership(league_id, user, db)
    league = await db.get(UserLeague, league_id)
    tournament = await db.get(Tournament, league.tournament_id) if league and league.tournament_id else None
    if not tournament:
        raise HTTPException(404, "Сначала выбери турнир")
    if tournament.provider != "sstats":
        raise HTTPException(503, "Таблица этого турнира пока недоступна")
    try:
        data = await standings_payload(tournament.provider_id, league.tournament_season)
    except Exception as exc:
        raise HTTPException(503, "Не удалось загрузить таблицу турнира. Попробуй ещё раз.") from exc
    ids = {r["teamId"] for t in data["tables"] for r in (t.get("rows") or [])}
    teams = (await db.scalars(select(Team).where(Team.provider == "sstats", Team.provider_id.in_(ids)))).all() if ids else []
    return {"name": tournament.name, "season": league.tournament_season,
            "groups": normalize_tables(data, {t.provider_id: t for t in teams}, tournament.provider_id == 2)}
