from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import get_current_user
from app.competitions.champions_league import classify_ucl_round
from app.database import get_db
from app.localization import normalize_team_name, team_logo_url, team_name_ru
from app.models import Match, Team, TournamentPrediction, User
from app.providers.sstats import SStatsProvider

router=APIRouter(prefix='/api/tournament-predictions',tags=['tournament-predictions'])
class TournamentPredictionBody(BaseModel):
 winner:str=Field(min_length=1,max_length=150);second_place:str=Field(min_length=1,max_length=150);third_place:str=Field(min_length=1,max_length=150);top_scorer:str=Field(min_length=1,max_length=150);top_assistant:str=Field(min_length=1,max_length=150);best_player:str=Field(min_length=1,max_length=150)
async def _main_stage_matches(db,provider,season):
 matches=(await db.execute(select(Match).where(Match.provider==provider,Match.season==season).order_by(Match.kickoff_at))).scalars().all()
 if provider=='sstats' and season==2026:return [m for m in matches if classify_ucl_round(season,m.kickoff_at) is not None]
 return matches
async def _deadline(db,provider,season):
 matches=await _main_stage_matches(db,provider,season)
 if not matches:raise HTTPException(404,'Tournament matches not found')
 if provider=='sstats' and season==2026:
  md1=[m.kickoff_at for m in matches if (classify_ucl_round(season,m.kickoff_at) or {}).get('stage')=='league_phase' and (classify_ucl_round(season,m.kickoff_at) or {}).get('matchday')==1]
  if md1:return min(md1)
 return matches[0].kickoff_at
def _out(p,deadline):
 now=datetime.now(timezone.utc);return {'provider':p.provider if p else None,'season':p.season if p else None,'deadline_at':deadline,'locked':now>=deadline,'prediction':None if not p else {'winner':p.winner,'second_place':p.second_place,'third_place':p.third_place,'top_scorer':p.top_scorer,'top_assistant':p.top_assistant,'best_player':p.best_player,'created_at':p.created_at,'updated_at':p.updated_at}}
async def _logo_catalog(db):
 rows=(await db.execute(select(Team).where(Team.logo_url.is_not(None)))).scalars().all();catalog={}
 for t in rows:
  key=normalize_team_name(t.name)
  if key and key not in catalog:catalog[key]=t.logo_url
 return catalog
async def _competition_teams(db,provider,season):
 matches=await _main_stage_matches(db,provider,season);ids={i for m in matches for i in (m.home_team_id,m.away_team_id) if i is not None}
 if not ids:return []
 teams=(await db.execute(select(Team).where(Team.id.in_(ids)).order_by(Team.name))).scalars().all();logos=await _logo_catalog(db)
 return [{'id':t.id,'provider_id':t.provider_id,'name':t.name,'display_name':team_name_ru(t.name),'logo':team_logo_url(t.name,t.logo_url or logos.get(normalize_team_name(t.name)))} for t in teams]
def _player_rows(payload):
 data=payload.get('data') or payload.get('response') or []
 if isinstance(data,dict):data=[data]
 out=[];seen=set()
 for x in data if isinstance(data,list) else []:
  if not isinstance(x,dict):continue
  pid=x.get('id',x.get('Id',x.get('playerId',x.get('PlayerId'))));name=x.get('name',x.get('Name',x.get('playerName',x.get('PlayerName',x.get('fullName',x.get('FullName'))))))
  if not name:continue
  key=(str(pid),str(name).lower())
  if key in seen:continue
  seen.add(key);team=x.get('teamName',x.get('TeamName'));position=x.get('position',x.get('Position',x.get('positionName',x.get('PositionName'))));out.append({'id':pid,'name':str(name),'team_original':team,'team':team_name_ru(team),'position':position,'photo':x.get('photo',x.get('Photo',x.get('image',x.get('Image'))))})
 return out[:30]
@router.get('/options/teams')
async def team_options(provider:str='sstats',season:int=2026,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
 items=await _competition_teams(db,provider,season);items.sort(key=lambda x:x['display_name']);return {'count':len(items),'response':items}
@router.get('/options/players')
async def player_options(q:str|None=Query(default=None,max_length=80),provider:str='sstats',season:int=2026,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
 p=SStatsProvider();payload={}
 try:
  if q and len(q.strip())>=2:payload=await p.find_players(q.strip())
  else:payload=await p.get_players(LeagueId=2,Year=season,Limit=30)
 except Exception:
  if q and len(q.strip())>=2:
   try:payload=await p.get_players(Name=q.strip())
   except Exception as e:raise HTTPException(502,f'Player search is temporarily unavailable: {type(e).__name__}')
 items=_player_rows(payload);teams=await _competition_teams(db,provider,season);logos={normalize_team_name(x['name']):x['logo'] for x in teams if x.get('logo')}
 for item in items:item['team_logo']=logos.get(normalize_team_name(item.get('team_original'))) or team_logo_url(item.get('team_original'),None)
 return {'count':len(items),'response':items}
@router.get('/mine')
async def mine(provider:str='sstats',season:int=2026,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
 deadline=await _deadline(db,provider,season);p=await db.scalar(select(TournamentPrediction).where(TournamentPrediction.user_id==user.id,TournamentPrediction.provider==provider,TournamentPrediction.season==season));r=_out(p,deadline);r['provider']=provider;r['season']=season;return r
@router.put('/mine')
async def save(body:TournamentPredictionBody,provider:str='sstats',season:int=2026,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
 deadline=await _deadline(db,provider,season);now=datetime.now(timezone.utc)
 if now>=deadline:raise HTTPException(409,'Tournament prediction deadline has passed')
 values={k:getattr(body,k).strip() for k in ('winner','second_place','third_place','top_scorer','top_assistant','best_player')};teams=await _competition_teams(db,provider,season);allowed={x['name'].casefold():x['name'] for x in teams}
 for k in ('winner','second_place','third_place'):
  canonical=allowed.get(values[k].casefold())
  if canonical is None:raise HTTPException(422,f'{values[k]} is not a team in this tournament')
  values[k]=canonical
 if len({values['winner'].casefold(),values['second_place'].casefold(),values['third_place'].casefold()})<3:raise HTTPException(422,'Winner, second and third place must be different teams')
 p=await db.scalar(select(TournamentPrediction).where(TournamentPrediction.user_id==user.id,TournamentPrediction.provider==provider,TournamentPrediction.season==season))
 if p is None:p=TournamentPrediction(user_id=user.id,provider=provider,season=season,deadline_at=deadline,**values);db.add(p)
 else:
  for k,v in values.items():setattr(p,k,v)
  p.deadline_at=deadline;p.updated_at=now
 await db.commit();await db.refresh(p);return _out(p,deadline)
