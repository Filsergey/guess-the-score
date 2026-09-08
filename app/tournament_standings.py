import asyncio
from datetime import datetime, timezone
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.leagues import _membership
from app.localization import round_name_ru, team_name_ru
from app.match_status import status_group, status_label_ru
from app.models import Match, Player, Team, Tournament, User, UserLeague
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
                    "team_id": team.id if team else None,
                    "provider_team_id": tid,
                    "rank": rank,
                    "name": team_name_ru(team.name) if team else team_name_ru(row.get("teamName") or f"Клуб №{tid}"),
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


def _match_out(m: Match, opponent: Team, is_home: bool):
    own_goals = m.home_goals if is_home else m.away_goals
    opp_goals = m.away_goals if is_home else m.home_goals
    result = None
    if status_group(m.status_short) == "finished" and own_goals is not None and opp_goals is not None:
        result = "W" if own_goals > opp_goals else "D" if own_goals == opp_goals else "L"
    return {
        "id": m.id,
        "kickoff_at": m.kickoff_at,
        "round": round_name_ru(m.round_name),
        "status": m.status_short,
        "status_group": status_group(m.status_short),
        "status_label": status_label_ru(m.status_short),
        "is_home": is_home,
        "own_goals": own_goals,
        "opponent_goals": opp_goals,
        "result": result,
        "opponent": {
            "id": opponent.id,
            "name": team_name_ru(opponent.name),
            "logo": f"/api/team-logo/db/{opponent.id}",
        },
    }


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


@router.get("/{league_id}/teams/{team_id}/overview")
async def team_overview(league_id: int, team_id: int, user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    await _membership(league_id, user, db)
    league = await db.get(UserLeague, league_id)
    if not league or not league.tournament_id:
        raise HTTPException(404, "Турнир лиги не найден")
    tournament = await db.get(Tournament, league.tournament_id)
    team = await db.get(Team, team_id)
    if not tournament or not team:
        raise HTTPException(404, "Клуб не найден")

    match_stmt = select(Match).where(
        Match.provider == league.tournament_provider,
        Match.season == league.tournament_season,
        Match.tournament_id == league.tournament_id,
        or_(Match.home_team_id == team.id, Match.away_team_id == team.id),
    ).order_by(Match.kickoff_at)
    matches = (await db.scalars(match_stmt)).all()
    if not matches:
        raise HTTPException(404, "У клуба нет матчей в выбранном турнире")

    opponent_ids = {m.away_team_id if m.home_team_id == team.id else m.home_team_id for m in matches}
    opponents = (await db.scalars(select(Team).where(Team.id.in_(opponent_ids)))).all() if opponent_ids else []
    by_team = {t.id: t for t in opponents}
    match_items = []
    for m in matches:
        is_home = m.home_team_id == team.id
        opponent_id = m.away_team_id if is_home else m.home_team_id
        opponent = by_team.get(opponent_id)
        if opponent:
            match_items.append(_match_out(m, opponent, is_home))

    finished = [x for x in match_items if x["status_group"] == "finished"]
    upcoming = [x for x in match_items if x["status_group"] in {"upcoming", "live"}]
    recent = list(reversed(finished[-5:]))
    form = [x["result"] for x in recent if x["result"]]

    now = datetime.now(timezone.utc)
    next_matches = [x for x in upcoming if x["kickoff_at"] >= now or x["status_group"] == "live"][:5]

    standing = None
    try:
        data = await standings_payload(tournament.provider_id, league.tournament_season)
        groups = normalize_tables(data, {team.provider_id: team}, tournament.provider_id == 2)
        for group in groups:
            for row in group["rows"]:
                if row.get("provider_team_id") == team.provider_id:
                    standing = {**row, "group": group["name"]}
                    break
            if standing:
                break
    except Exception:
        standing = None

    players = (await db.scalars(
        select(Player).where(
            Player.provider == "sstats",
            Player.team_provider_id == team.provider_id,
            Player.is_active.is_(True),
        ).order_by(Player.shirt_number.is_(None), Player.shirt_number, Player.name)
    )).all()
    squad = [{
        "id": p.id,
        "provider_id": p.provider_id,
        "name": p.display_name or p.name,
        "position": p.position,
        "number": p.shirt_number,
        "nationality": p.nationality,
        "photo": f"/api/players/{p.id}/photo" if (p.photo_data or p.photo_source_url or p.has_photo) else None,
    } for p in players]

    return {
        "team": {
            "id": team.id,
            "provider_id": team.provider_id,
            "name": team_name_ru(team.name),
            "code": team.code,
            "country_code": team.country_code,
            "logo": f"/api/team-logo/db/{team.id}",
        },
        "tournament": {"id": tournament.id, "name": tournament.name, "season": league.tournament_season},
        "standing": standing,
        "form": form,
        "recent_matches": recent,
        "next_matches": next_matches,
        "squad": squad,
    }
