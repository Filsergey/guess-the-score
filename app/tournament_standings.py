import asyncio
from datetime import datetime, timezone
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.competitions.champions_league import classify_ucl_round
from app.database import get_db
from app.leagues import _membership
from app.localization import round_name_ru, team_name_ru
from app.match_status import FINAL_MATCH_STATUSES, status_group, status_label_ru
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


async def _local_finished_stats(db: AsyncSession, tournament_db_id: int, season: int, is_ucl: bool = False):
    """Build standings from already synced finished fixtures.

    For the Champions League table only league-phase fixtures count. Qualifying
    rounds and all knockout rounds must never affect the 36-team league table.
    """
    matches = (await db.scalars(
        select(Match).where(
            Match.provider == "sstats",
            Match.tournament_id == tournament_db_id,
            Match.season == season,
            Match.status_short.in_(tuple(FINAL_MATCH_STATUSES)),
            Match.home_goals.is_not(None),
            Match.away_goals.is_not(None),
        )
    )).all()

    if is_ucl:
        matches = [
            match for match in matches
            if (classify_ucl_round(match.season, match.kickoff_at) or {}).get("stage") == "league_phase"
        ]

    if not matches:
        return {}, 0

    team_ids = {m.home_team_id for m in matches} | {m.away_team_id for m in matches}
    teams = (await db.scalars(select(Team).where(Team.id.in_(team_ids)))).all()
    provider_id_by_db = {t.id: t.provider_id for t in teams if t.provider == "sstats"}
    stats = {}

    def row(provider_id):
        return stats.setdefault(provider_id, {
            "played": 0, "wins": 0, "draws": 0, "losses": 0,
            "goals_for": 0, "goals_against": 0, "points": 0,
        })

    covered = 0
    for match in matches:
        home_id = provider_id_by_db.get(match.home_team_id)
        away_id = provider_id_by_db.get(match.away_team_id)
        if home_id is None or away_id is None:
            continue
        hg, ag = int(match.home_goals), int(match.away_goals)
        home, away = row(home_id), row(away_id)
        home["played"] += 1
        away["played"] += 1
        home["goals_for"] += hg
        home["goals_against"] += ag
        away["goals_for"] += ag
        away["goals_against"] += hg
        if hg > ag:
            home["wins"] += 1
            away["losses"] += 1
            home["points"] += 3
        elif hg < ag:
            away["wins"] += 1
            home["losses"] += 1
            away["points"] += 3
        else:
            home["draws"] += 1
            away["draws"] += 1
            home["points"] += 1
            away["points"] += 1
        covered += 1

    return stats, covered


def normalize_tables(data, team_map, is_ucl, local_stats=None):
    groups = []
    local_stats = local_stats or {}
    for table in data.get("tables", []):
        rows = table.get("rows") or []
        by_group = {}
        for row in rows:
            by_group.setdefault(row.get("groupName") or "Турнирная таблица", []).append(row)
        for name, items in by_group.items():
            league_phase = is_ucl and str(name).casefold() == "league phase" and len(items) == 36
            provider_played = sum(int(x.get("played") or 0) for x in items)
            local_played = sum(int(local_stats.get(x.get("teamId"), {}).get("played") or 0) for x in items)
            use_local = bool(local_stats) and local_played > provider_played

            prepared = []
            for row in items:
                tid = row["teamId"]
                local = local_stats.get(tid) if use_local else None
                gf = local["goals_for"] if local else row.get("goalsFor")
                ga = local["goals_against"] if local else row.get("goalsAgainst")
                prepared.append({
                    "raw": row,
                    "team_id": tid,
                    "played": local["played"] if local else row.get("played"),
                    "wins": local["wins"] if local else row.get("wins"),
                    "draws": local["draws"] if local else row.get("draws"),
                    "losses": local["losses"] if local else row.get("loses"),
                    "goals_for": gf,
                    "goals_against": ga,
                    "difference": (gf - ga) if gf is not None and ga is not None else None,
                    "points": local["points"] if local else row.get("points"),
                })

            if use_local:
                prepared.sort(key=lambda x: (
                    -int(x["points"] or 0),
                    -int(x["difference"] or 0),
                    -int(x["goals_for"] or 0),
                    -int(x["wins"] or 0),
                    int(x["raw"].get("rank") or 999),
                ))
            else:
                prepared.sort(key=lambda x: int(x["raw"].get("rank") or 999))

            output = []
            for index, item in enumerate(prepared, 1):
                row = item["raw"]
                tid = item["team_id"]
                team = team_map.get(tid)
                rank = index if use_local else row["rank"]
                output.append({
                    "team_id": team.id if team else None,
                    "provider_team_id": tid,
                    "rank": rank,
                    "name": team_name_ru(team.name) if team else team_name_ru(row.get("teamName") or f"Клуб №{tid}"),
                    "logo": f"/api/team-logo/db/{team.id}" if team else None,
                    "played": item["played"], "wins": item["wins"],
                    "draws": item["draws"], "losses": item["losses"],
                    "goals_for": item["goals_for"], "goals_against": item["goals_against"],
                    "difference": item["difference"], "points": item["points"],
                    "zone": ("direct" if rank <= 8 else "playoff" if rank <= 24 else "out") if league_phase else None,
                })
            groups.append({"name": "Общий этап" if league_phase else name,
                           "ucl_zones": league_phase, "rows": output,
                           "calculated_locally": use_local})
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
    is_ucl = tournament.provider_id == 2
    local_stats, finished_count = await _local_finished_stats(
        db, tournament.id, league.tournament_season, is_ucl=is_ucl
    )
    groups = normalize_tables(data, {t.provider_id: t for t in teams}, is_ucl, local_stats)
    locally_calculated = any(g.get("calculated_locally") for g in groups)
    return {"name": tournament.name, "season": league.tournament_season,
            "groups": groups, "source": "local-finished" if locally_calculated else "sstats",
            "finished_matches": finished_count}


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
