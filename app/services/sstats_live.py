from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.match_status import FINAL_MATCH_STATUSES, LIVE_MATCH_STATUSES
from app.models import Match
from app.providers.sstats import SStatsProvider
from app.services.sstats_sync import _normalize_status, _pick


def _rows(payload:dict)->list[dict]:
    rows=payload.get("data") or payload.get("response") or []
    if isinstance(rows,dict):rows=[rows]
    return [SStatsProvider._normalize_game(x) for x in rows if isinstance(x,dict)]

def _first(payload:dict)->dict:
    data=payload.get("data") or payload.get("response") or {}
    if isinstance(data,list):data=data[0] if data else {}
    if not isinstance(data,dict):return {}
    game=data.get("game") if isinstance(data.get("game"),dict) else data
    return SStatsProvider._normalize_game(game)

def _int(value):
    try:return int(value) if value is not None and value!="" else None
    except (TypeError,ValueError):return None

def _apply(match:Match,row:dict)->bool:
    short,long_name=_normalize_status(_pick(row,"status","Status"),_pick(row,"statusName","StatusName"));home=_int(_pick(row,"scoreHome","ScoreHome","homeResult","HomeResult"));away=_int(_pick(row,"scoreAway","ScoreAway","awayResult","AwayResult"));elapsed=_int(_pick(row,"elapsed","Elapsed","minute","Minute"));before=(match.status_short,match.status_long,match.home_goals,match.away_goals,match.elapsed);match.status_short=short;match.status_long=long_name
    if home is not None:match.home_goals=home
    if away is not None:match.away_goals=away
    if elapsed is not None:match.elapsed=elapsed
    return before!=(match.status_short,match.status_long,match.home_goals,match.away_goals,match.elapsed)

async def sync_sstats_live_matches(db:AsyncSession,season:int)->dict:
    """Refresh live UCL games and re-check DB-live games that disappeared from Live=true.

    SStats can remove a game from the Live=true result immediately after FT. Re-checking
    only those matches that our DB still considers live captures the final transition
    without waiting for the hourly full competition sync.
    """
    provider=SStatsProvider();season_info=await provider.resolve_season_uid(2,season);kwargs={"season_uid":season_info["uid"]} if season_info and season_info.get("uid") else {"league_id":2,"year":season};payload=await provider.get_games(**kwargs,live=True,limit=1000);rows=_rows(payload);live_ids={str(_pick(row,"id","Id")) for row in rows if _pick(row,"id","Id") is not None}
    db_live=(await db.execute(select(Match).where(Match.provider=="sstats",Match.season==season,Match.status_short.in_(tuple(LIVE_MATCH_STATUSES))))).scalars().all();db_live_by_id={str(m.provider_id):m for m in db_live}
    incoming_ids=list(live_ids);incoming_matches=(await db.execute(select(Match).where(Match.provider=="sstats",Match.provider_id.in_(incoming_ids)))).scalars().all() if incoming_ids else [];by_provider_id={str(m.provider_id):m for m in incoming_matches};changed=0
    for row in rows:
        match=by_provider_id.get(str(_pick(row,"id","Id")))
        if match:changed+=int(_apply(match,row))
    stale=[m for pid,m in db_live_by_id.items() if pid not in live_ids];stale_checked=finished_captured=0;stale_errors=[]
    for match in stale:
        try:
            row=_first(await provider.get_game(int(match.provider_id)));stale_checked+=1
            if row:
                was_live=match.status_short in LIVE_MATCH_STATUSES;changed_now=_apply(match,row);changed+=int(changed_now)
                if was_live and match.status_short in FINAL_MATCH_STATUSES:finished_captured+=1
        except Exception as exc:
            if len(stale_errors)<5:stale_errors.append({"match_id":match.id,"provider_id":str(match.provider_id),"error":type(exc).__name__})
    await db.commit()
    return {"season":season,"live_received":len(rows),"live_matched":len(incoming_matches),"db_live_before":len(db_live),"stale_live_candidates":len(stale),"stale_live_checked":stale_checked,"finished_captured":finished_captured,"changed":changed,"live_ids":sorted(live_ids),"stale_errors":stale_errors,"synced_at":datetime.now(timezone.utc).isoformat()}
