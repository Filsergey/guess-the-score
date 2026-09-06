from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.match_status import FINAL_MATCH_STATUSES, LIVE_MATCH_STATUSES
from app.models import Match, Tournament, UserLeague
from app.providers.sstats import SStatsProvider
from app.services.push_notifications import process_push_notifications
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
    changed=before!=(match.status_short,match.status_long,match.home_goals,match.away_goals,match.elapsed)
    if changed:match.updated_at=datetime.now(timezone.utc)
    return changed


async def _competition_scopes(db:AsyncSession,fallback_season:int)->list[tuple[int,int,int]]:
    """Return (tournament_db_id, sstats_league_id, season) for tournaments actually used by user leagues."""
    rows=(await db.execute(
        select(Tournament.id,Tournament.provider_id,UserLeague.tournament_season)
        .join(UserLeague,UserLeague.tournament_id==Tournament.id)
        .where(Tournament.provider=="sstats",UserLeague.tournament_provider=="sstats",UserLeague.tournament_id.is_not(None))
        .distinct()
    )).all()
    scopes={(int(tid),int(provider_id),int(season)) for tid,provider_id,season in rows if tid is not None and provider_id is not None and season is not None}
    if not scopes:
        ucl=await db.scalar(select(Tournament).where(Tournament.provider=="sstats",Tournament.provider_id==2))
        if ucl is not None:scopes.add((ucl.id,2,int(fallback_season)))
    return sorted(scopes,key=lambda x:(x[2],x[1],x[0]))


async def sync_sstats_live_matches(db:AsyncSession,season:int)->dict:
    """Refresh LIVE games while keeping SStats request volume bounded.

    LeagueId + Year is supported directly by Games/list, so we deliberately avoid
    resolving /Leagues on every 30-second tick. Only a small number of near-kickoff
    matches are checked individually as a fallback for delayed Live=true results.
    """
    provider=SStatsProvider();scopes=await _competition_scopes(db,season);now=datetime.now(timezone.utc);changed=live_received=live_matched=stale_checked=finished_captured=kickoff_checked=0;live_ids=set();errors=[];scope_results=[]

    for tournament_id,league_id,scope_season in scopes:
        try:
            payload=await provider.get_games(league_id=league_id,year=scope_season,live=True,limit=1000)
            rows=_rows(payload);scope_live_ids={str(_pick(row,"id","Id")) for row in rows if _pick(row,"id","Id") is not None};live_ids.update(scope_live_ids);live_received+=len(rows)
            incoming=list(scope_live_ids)
            matches=(await db.execute(select(Match).where(Match.provider=="sstats",Match.tournament_id==tournament_id,Match.provider_id.in_(incoming)))).scalars().all() if incoming else []
            by_provider_id={str(m.provider_id):m for m in matches};live_matched+=len(matches);scope_changed=0
            for row in rows:
                match=by_provider_id.get(str(_pick(row,"id","Id")))
                if match:
                    did=_apply(match,row);changed+=int(did);scope_changed+=int(did)
            scope_results.append({"league_id":league_id,"season":scope_season,"tournament_id":tournament_id,"live_received":len(rows),"live_matched":len(matches),"changed":scope_changed})
        except Exception as exc:
            if len(errors)<12:errors.append({"league_id":league_id,"season":scope_season,"stage":"live-list","error":type(exc).__name__})

    scope_tournament_ids={t for t,_,_ in scopes}
    scope_seasons={s for _,_,s in scopes}
    db_live=(await db.execute(select(Match).where(Match.provider=="sstats",Match.tournament_id.in_(scope_tournament_ids),Match.season.in_(scope_seasons),Match.status_short.in_(tuple(LIVE_MATCH_STATUSES))))).scalars().all() if scope_tournament_ids else []

    # A DB-live match that vanished from Live=true may just have finished. Limit these
    # detail requests too, because each Games/{id} consumes one SStats request.
    for match in db_live[:4]:
        if str(match.provider_id) in live_ids:continue
        try:
            row=_first(await provider.get_game(int(match.provider_id)));stale_checked+=1
            if row:
                was_live=match.status_short in LIVE_MATCH_STATUSES;did=_apply(match,row);changed+=int(did)
                if was_live and match.status_short in FINAL_MATCH_STATUSES:finished_captured+=1
        except Exception as exc:
            if len(errors)<12:errors.append({"match_id":match.id,"provider_id":str(match.provider_id),"stage":"stale-live","error":type(exc).__name__})

    # Domestic competitions sometimes lag in Live=true. Probe only the nearest few
    # kickoffs instead of up to twenty games every 30 seconds.
    if scope_tournament_ids:
        candidates=(await db.execute(
            select(Match).where(
                Match.provider=="sstats",
                Match.tournament_id.in_(scope_tournament_ids),
                Match.season.in_(scope_seasons),
                Match.kickoff_at>=now-timedelta(hours=3),
                Match.kickoff_at<=now+timedelta(minutes=10),
                ~Match.status_short.in_(tuple(FINAL_MATCH_STATUSES)),
            ).order_by(Match.kickoff_at).limit(4)
        )).scalars().all()
        for match in candidates:
            if str(match.provider_id) in live_ids:continue
            try:
                row=_first(await provider.get_game(int(match.provider_id)));kickoff_checked+=1
                if row:changed+=int(_apply(match,row))
            except Exception as exc:
                if len(errors)<12:errors.append({"match_id":match.id,"provider_id":str(match.provider_id),"stage":"kickoff-window","error":type(exc).__name__})

    await db.commit()
    try:
        push=await process_push_notifications(db)
    except Exception as exc:
        push={"configured":False,"sent":0,"error":type(exc).__name__}
    return {"season_fallback":season,"competitions":len(scopes),"scopes":scope_results,"live_received":live_received,"live_matched":live_matched,"db_live_before":len(db_live),"stale_live_checked":stale_checked,"kickoff_window_checked":kickoff_checked,"finished_captured":finished_captured,"changed":changed,"live_ids":sorted(live_ids),"errors":errors,"push":push,"synced_at":datetime.now(timezone.utc).isoformat()}
