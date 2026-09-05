from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import get_current_user
from app.database import get_db
from app.models import Match, Team, TournamentPrediction, User
from app.providers.sstats import SStatsProvider

router=APIRouter(prefix='/api/tournament-predictions',tags=['tournament-predictions'])
class TournamentPredictionBody(BaseModel):
 winner:str=Field(min_length=1,max_length=150);second_place:str=Field(min_length=1,max_length=150);third_place:str=Field(min_length=1,max_length=150);top_scorer:str=Field(min_length=1,max_length=150);top_assistant:str=Field(min_length=1,max_length=150);best_player:str=Field(min_length=1,max_length=150)
async def _deadline(db,provider,season):
 d=await db.scalar(select(Match.kickoff_at).where(Match.provider==provider,Match.season==season).order_by(Match.kickoff_at).limit(1))
 if d is None:raise HTTPException(404,'Tournament matches not found')
 return d
def _out(p,deadline):
 now=datetime.now(timezone.utc);return {'provider':p.provider if p else None,'season':p.season if p else None,'deadline_at':deadline,'locked':now>=deadline,'prediction':None if not p else {'winner':p.winner,'second_place':p.second_place,'third_place':p.third_place,'top_scorer':p.top_scorer,'top_assistant':p.top_assistant,'best_player':p.best_player,'created_at':p.created_at,'updated_at':p.updated_at}}
async def _competition_teams(db,provider,season):
 rows=(await db.execute(select(Match.home_team_id,Match.away_team_id).where(Match.provider==provider,Match.season==season))).all();ids={i for r in rows for i in r if i is not None}
 if not ids:return []
 teams=(await db.execute(select(Team).where(Team.id.in_(ids)).order_by(Team.name))).scalars().all();return [{'id':t.id,'provider_id':t.provider_id,'name':t.name,'logo':t.logo_url} for t in teams]
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
  seen.add(key);out.append({'id':pid,'name':str(name),'team':x.get('teamName',x.get('TeamName')),'photo':x.get('photo',x.get('Photo'))})
 return out[:20]
@router.get('/options/teams')
async def team_options(provider:str='sstats',season:int=2026,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
 items=await _competition_teams(db,provider,season);return {'count':len(items),'response':items}
@router.get('/options/players')
async def player_options(q:str=Query(min_length=2,max_length=80),user:User=Depends(get_current_user)):
 p=SStatsProvider()
 try:payload=await p.find_players(q)
 except Exception:
  try:payload=await p.get_players(Name=q)
  except Exception as e:raise HTTPException(502,f'Player search is temporarily unavailable: {type(e).__name__}')
 items=_player_rows(payload);return {'count':len(items),'response':items}
@router.get('/mine')
async def mine(provider:str='sstats',season:int=2026,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
 deadline=await _deadline(db,provider,season);p=await db.scalar(select(TournamentPrediction).where(TournamentPrediction.user_id==user.id,TournamentPrediction.provider==provider,TournamentPrediction.season==season));r=_out(p,deadline);r['provider']=provider;r['season']=season;return r
@router.put('/mine')
async def save(body:TournamentPredictionBody,provider:str='sstats',season:int=2026,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
 deadline=await _deadline(db,provider,season);now=datetime.now(timezone.utc)
 if now>=deadline:raise HTTPException(409,'Tournament prediction deadline has passed')
 values={k:getattr(body,k).strip() for k in ('winner','second_place','third_place','top_scorer','top_assistant','best_player')}
 teams=await _competition_teams(db,provider,season);allowed={x['name'].casefold():x['name'] for x in teams}
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
