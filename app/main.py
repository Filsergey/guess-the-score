import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from app.auth import router as auth_router
from app.competitions.champions_league import classify_ucl_round
from app.config import get_settings
from app.database import engine, get_db
from app.leagues import router as leagues_router
from app.migrations import migrate_provider_keys
from app.models import Base, Match, Team
from app.oracle import router as oracle_router
from app.predictions import router as predictions_router
from app.providers.api_football import APIFootballProvider
from app.providers.sstats import SStatsProvider
from app.services.football_sync import sync_champions_league
from app.services.oracle_scheduler import oracle_scheduler_loop
from app.services.sstats_sync import sync_sstats_champions_league, sync_sstats_team_metadata
settings=get_settings();STATIC_DIR=Path(__file__).resolve().parent/'static'
@asynccontextmanager
async def lifespan(_:FastAPI):
 async with engine.begin() as conn:await conn.run_sync(Base.metadata.create_all);await migrate_provider_keys(conn)
 scheduler_task=None
 if settings.oracle_scheduler_enabled:
  scheduler_task=asyncio.create_task(oracle_scheduler_loop())
 try:
  yield
 finally:
  if scheduler_task:
   scheduler_task.cancel()
   with suppress(asyncio.CancelledError):await scheduler_task
app=FastAPI(title=settings.app_name,version='0.11.3',lifespan=lifespan);app.include_router(auth_router);app.include_router(predictions_router);app.include_router(leagues_router);app.include_router(oracle_router);app.mount('/static',StaticFiles(directory=STATIC_DIR),name='static')
@app.get('/',include_in_schema=False,response_class=HTMLResponse)
async def mini_app():
 html=(STATIC_DIR/'index.html').read_text(encoding='utf-8');return HTMLResponse(html.replace('</body>','<script src="/static/oracle-ui.js?v=4"></script><script src="/static/oracle-leaderboard.js?v=1"></script><script src="/static/prediction-history.js?v=1"></script><script src="/static/leaderboard-me.js?v=1"></script></body>'))
def require_admin_token(x_admin_token):
 if not settings.admin_sync_token:raise HTTPException(503,'ADMIN_SYNC_TOKEN is not configured')
 if x_admin_token!=settings.admin_sync_token:raise HTTPException(401,'Invalid admin token')
def serialize_match(m,h,a):
 c=classify_ucl_round(m.season,m.kickoff_at) if m.provider=='sstats' else None;r=m.round_name or (c['round_label'] if c else None);return {'id':m.id,'provider':m.provider,'provider_id':m.provider_id,'season':m.season,'round':r,'kickoff_at':m.kickoff_at,'status':m.status_short,'status_source':m.status_long,'elapsed':m.elapsed,'home':{'id':h.id,'provider':h.provider,'provider_id':h.provider_id,'name':h.name,'code':h.code,'logo':h.logo_url,'goals':m.home_goals},'away':{'id':a.id,'provider':a.provider,'provider_id':a.provider_id,'name':a.name,'code':a.code,'logo':a.logo_url,'goals':m.away_goals}}
def _first_item(p):
 d=p.get('data') or p.get('response') or [];return (d[0] if d else {}) if isinstance(d,list) else (d if isinstance(d,dict) else {})
def _v(d,n):return d.get(n[:1].lower()+n[1:],d.get(n))
def _merge_non_empty(a,b):r=dict(b);r.update({k:v for k,v in a.items() if v is not None});return r
def serialize_sstats_details(d,g=None):
 g=g or {};names=['ShotsOnGoal','ShotsOffGoal','TotalShots','BlockedShots','ShotsInsideBox','ShotsOutsideBox','Fouls','CornerKicks','BallPossession','YellowCards','RedCards','GoalkeeperSaves','TotalPasses','PassesAccurate','Offsides','ExpectedGoals','CalculatedXg'];stats={n:{'home':_v(d,n+'Home'),'away':_v(d,n+'Away')} for n in names};return {'flash_id':_v(d,'FlashId'),'season_uid':_v(d,'SeasonUid'),'coverage':_v(d,'Coverage'),'venue':{'id':_v(d,'VenueId'),'name':_v(d,'VenueName'),'city':_v(d,'VenueCity'),'address':_v(d,'VenueAddress')},'coaches':{'home':_v(d,'HomeTeamCoachName'),'away':_v(d,'AwayTeamCoachName')},'score':{'ht':{'home':_v(d,'ScoreHomeHT'),'away':_v(d,'ScoreAwayHT')},'ft':{'home':_v(d,'ScoreHomeFT'),'away':_v(d,'ScoreAwayFT')},'et':{'home':_v(d,'ScoreHomeET'),'away':_v(d,'ScoreAwayET')},'penalties':{'home':_v(d,'ScoreHomePT'),'away':_v(d,'ScoreAwayPT')}},'odds':{'home':_v(d,'Winner1'),'draw':_v(d,'WinnerX'),'away':_v(d,'Winner2')},'model':{'rating':{'home':_v(d,'GlickoRatingHome') or _v(g,'RatingHome'),'away':_v(d,'GlickoRatingAway') or _v(g,'RatingAway')},'win_probability':{'home':_v(d,'GlickoWinProbHome') or _v(g,'WinProbHome'),'away':_v(d,'GlickoWinProbAway') or _v(g,'WinProbAway')},'xg':{'home':_v(d,'GlickoXgHome') or _v(g,'XgHome'),'away':_v(d,'GlickoXgAway') or _v(g,'XgAway')},'odds_xg':{'home':_v(d,'OddsXgHome'),'away':_v(d,'OddsXgAway')}},'statistics':stats}
@app.get('/health')
async def health():return {'status':'ok','service':settings.app_name,'environment':settings.app_env}
@app.get('/api/admin/football/leagues')
async def football_leagues(x_admin_token:str|None=Header(default=None)):
 require_admin_token(x_admin_token);return await APIFootballProvider().get_leagues()
@app.get('/api/admin/sstats/leagues')
async def sstats_leagues(x_admin_token:str|None=Header(default=None)):
 require_admin_token(x_admin_token);return await SStatsProvider().get_leagues()
@app.get('/api/admin/sstats/games')
async def sstats_games(league_id:int=Query(default=2,ge=1),year:int=Query(...,ge=2020,le=2100),x_admin_token:str|None=Header(default=None)):
 require_admin_token(x_admin_token);return await SStatsProvider().get_games(league_id,year)
@app.get('/api/admin/sstats/games/{game_id}')
async def sstats_game(game_id:int,x_admin_token:str|None=Header(default=None)):
 require_admin_token(x_admin_token);return await SStatsProvider().get_game(game_id)
@app.get('/api/admin/sstats/teams/{team_id}')
async def sstats_team(team_id:int,x_admin_token:str|None=Header(default=None)):
 require_admin_token(x_admin_token);return await SStatsProvider().get_team(team_id)
@app.post('/api/admin/sync/sstats/champions-league')
async def sync_sstats_champions_league_endpoint(year:int=Query(...,ge=2020,le=2100),x_admin_token:str|None=Header(default=None),db:AsyncSession=Depends(get_db)):
 require_admin_token(x_admin_token)
 try:return await sync_sstats_champions_league(db,year)
 except Exception as e:await db.rollback();raise HTTPException(502,f'SStats Champions League sync failed: {type(e).__name__}')
@app.post('/api/admin/sync/sstats/team-metadata')
async def sync_sstats_team_metadata_endpoint(limit:int=Query(default=20,ge=1,le=25),x_admin_token:str|None=Header(default=None),db:AsyncSession=Depends(get_db)):
 require_admin_token(x_admin_token)
 try:return await sync_sstats_team_metadata(db,limit)
 except Exception as e:await db.rollback();raise HTTPException(502,f'SStats team metadata sync failed: {type(e).__name__}')
@app.post('/api/admin/sync/champions-league')
async def sync_champions_league_endpoint(season:int=Query(...,ge=2020,le=2100),x_admin_token:str|None=Header(default=None),db:AsyncSession=Depends(get_db)):
 require_admin_token(x_admin_token)
 try:return await sync_champions_league(db,season)
 except Exception:await db.rollback();raise HTTPException(502,'Champions League sync failed')
@app.get('/api/matches')
async def matches(season:int|None=Query(default=None,ge=2020,le=2100),provider:str|None=Query(default=None),status:str|None=Query(default=None),db:AsyncSession=Depends(get_db)):
 h,a=aliased(Team),aliased(Team);q=select(Match,h,a).join(h,Match.home_team_id==h.id).join(a,Match.away_team_id==a.id).order_by(Match.kickoff_at)
 if season is not None:q=q.where(Match.season==season)
 if provider is not None:q=q.where(Match.provider==provider)
 if status is not None:q=q.where(Match.status_short==status.upper())
 rows=(await db.execute(q)).all();return {'count':len(rows),'response':[serialize_match(*r) for r in rows]}
async def _match_row(match_id,db):
 h,a=aliased(Team),aliased(Team);return (await db.execute(select(Match,h,a).join(h,Match.home_team_id==h.id).join(a,Match.away_team_id==a.id).where(Match.id==match_id))).first()
@app.get('/api/matches/{match_id}')
async def match_detail(match_id:int,db:AsyncSession=Depends(get_db)):
 r=await _match_row(match_id,db)
 if not r:raise HTTPException(404,'Match not found')
 return serialize_match(*r)
@app.get('/api/matches/{match_id}/details')
async def match_rich_detail(match_id:int,db:AsyncSession=Depends(get_db)):
 r=await _match_row(match_id,db)
 if not r:raise HTTPException(404,'Match not found')
 m,h,a=r;base=serialize_match(m,h,a)
 if m.provider!='sstats':return {**base,'details_available':False,'details_source':None,'details_errors':[],'details':None}
 p=SStatsProvider();qd={};gd={};gl={};errors=[]
 try:qd=_first_item(await p.query_game_details(m.provider_id))
 except Exception as e:errors.append(f'query:{type(e).__name__}')
 if not qd:
  try:gd=_first_item(await p.get_game(m.provider_id))
  except Exception as e:errors.append(f'game:{type(e).__name__}')
 try:gl=_first_item(await p.get_glicko(m.provider_id))
 except Exception as e:errors.append(f'glicko:{type(e).__name__}')
 d=_merge_non_empty(qd,gd) if (qd or gd) else {}
 if not d and not gl:return {**base,'details_available':False,'details_source':None,'details_errors':errors,'details':None}
 source='games/query' if qd else 'games/{id}';source+='+glicko' if gl else ''
 return {**base,'details_available':True,'details_source':source,'details_errors':errors,'details':serialize_sstats_details(d,gl)}
