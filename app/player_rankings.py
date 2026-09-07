"""Cached player goals and assists from SStats match events."""
import asyncio
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import DateTime, ForeignKey, Text, select
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Base, Match, Team, Tournament, UserLeague, User
from app.database import get_db
from app.auth import get_current_user
from app.leagues import _membership
from app.providers.sstats import SStatsProvider

class PlayerRankingMatch(Base):
    __tablename__ = "player_ranking_matches"
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True)
    payload: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

router = APIRouter(prefix="/api/leagues", tags=["player-rankings"])
_lock = asyncio.Lock()

def match_players(full):
    rows = {}
    def person(p, team):
        if not p or not p.get("id"):
            return None
        pid = int(p["id"])
        return rows.setdefault(pid, {"id":pid, "name":p.get("name") or f"Игрок №{pid}", "team_id":team, "goals":0, "assists":0})
    seen = set()
    for e in full.get("events") or []:
        if e.get("id") is not None:
            if e["id"] in seen: continue
            seen.add(e["id"])
        if str(e.get("type")) != "1" or e.get("name") not in ("Normal Goal", "Penalty"):
            continue
        scorer = person(e.get("player"), e.get("teamId"))
        if scorer: scorer["goals"] += 1
        assistant = person(e.get("assistPlayer"), e.get("teamId"))
        if assistant: assistant["assists"] += 1
    return list(rows.values())

@router.get("/{league_id}/player-rankings")
async def rankings(league_id:int, user:User=Depends(get_current_user), db:AsyncSession=Depends(get_db)):
    await _membership(league_id,user,db)
    league=await db.get(UserLeague,league_id)
    tournament=await db.get(Tournament,league.tournament_id) if league and league.tournament_id else None
    if not tournament or tournament.provider != "sstats":
        raise HTTPException(404,"Статистика игроков этого турнира недоступна")
    matches=(await db.scalars(select(Match).where(
        Match.tournament_id==tournament.id, Match.provider=="sstats",
        Match.season==league.tournament_season, Match.status_short.in_(("FT","AET","PEN"))
    ).order_by(Match.kickoff_at))).all()
    # The Champions League rankings cover the main competition, not qualification.
    if tournament.provider_id==2:
        matches=[m for m in matches if not any(x in (m.round_name or "").lower() for x in ("qualif","preliminary")) and (m.round_name or "").lower() not in ("play-offs","play-offs - 1st leg","play-offs - 2nd leg")]
    now=datetime.now(timezone.utc)
    async with _lock:
        saved={r.match_id:r for r in (await db.scalars(select(PlayerRankingMatch).where(PlayerRankingMatch.match_id.in_([m.id for m in matches])))).all()} if matches else {}
        pending=[m for m in matches if m.id not in saved or (now-saved[m.id].updated_at.replace(tzinfo=timezone.utc)).total_seconds()>(86400 if json.loads(saved[m.id].payload).get("covered") else 600)]
        semaphore=asyncio.Semaphore(4)
        async def fetch(m):
            async with semaphore:
                try:
                    p=await SStatsProvider()._get(f"Games/{m.provider_id}",timeout=5)
                    full=p.get("data") or {}
                    events=full.get("events")
                    goal_events=[e for e in (events or []) if str(e.get("type"))=="1" and e.get("name") in ("Normal Goal","Penalty","Own Goal")]
                    covered=isinstance(events,list) and m.home_goals is not None and m.away_goals is not None and len(goal_events)==m.home_goals+m.away_goals
                    covered=covered and all(e.get("name")=="Own Goal" or (e.get("player") or {}).get("id") for e in goal_events)
                    return m,{"rows":match_players(full),"covered":covered}
                except Exception:
                    return m,{"rows":[],"covered":False}
        for m, payload in await asyncio.gather(*(fetch(m) for m in pending[:8])):
            record=saved.get(m.id)
            if record is None:
                record=PlayerRankingMatch(match_id=m.id);db.add(record);saved[m.id]=record
            record.payload=json.dumps(payload,ensure_ascii=False);record.updated_at=now
        await db.commit()
    totals={};covered=0
    for m in matches:
        if m.id not in saved: continue
        payload=json.loads(saved[m.id].payload)
        covered+=int(payload["covered"])
        for row in payload["rows"]:
            current=totals.setdefault(row["id"],dict(row,goals=0,assists=0,team_ids=set()))
            current["goals"]+=row["goals"];current["assists"]+=row["assists"]
            current["team_ids"].add(row["team_id"])
    ids={tid for row in totals.values() for tid in row["team_ids"] if tid}
    teams={t.provider_id:t.name for t in (await db.scalars(select(Team).where(Team.provider=="sstats",Team.provider_id.in_(ids)))).all()} if ids else {}
    for row in totals.values():
        row["club"]=" / ".join(teams.get(t,f"Клуб №{t}") for t in sorted(row.pop("team_ids"),key=str))
    return {"rows":list(totals.values()),"total":len(matches),"covered":covered,"pending":max(0,len(pending)-8)}
