from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import get_current_user
from app.database import get_db
from app.models import Match, TournamentPrediction, User

router=APIRouter(prefix='/api/tournament-predictions',tags=['tournament-predictions'])
class TournamentPredictionBody(BaseModel):
 winner:str=Field(min_length=1,max_length=150);second_place:str=Field(min_length=1,max_length=150);third_place:str=Field(min_length=1,max_length=150);top_scorer:str=Field(min_length=1,max_length=150);top_assistant:str=Field(min_length=1,max_length=150);best_player:str=Field(min_length=1,max_length=150)
async def _deadline(db,provider,season):
 d=await db.scalar(select(Match.kickoff_at).where(Match.provider==provider,Match.season==season).order_by(Match.kickoff_at).limit(1))
 if d is None:raise HTTPException(404,'Tournament matches not found')
 return d
def _out(p,deadline):
 now=datetime.now(timezone.utc);return {'provider':p.provider if p else None,'season':p.season if p else None,'deadline_at':deadline,'locked':now>=deadline,'prediction':None if not p else {'winner':p.winner,'second_place':p.second_place,'third_place':p.third_place,'top_scorer':p.top_scorer,'top_assistant':p.top_assistant,'best_player':p.best_player,'created_at':p.created_at,'updated_at':p.updated_at}}
@router.get('/mine')
async def mine(provider:str='sstats',season:int=2026,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
 deadline=await _deadline(db,provider,season);p=await db.scalar(select(TournamentPrediction).where(TournamentPrediction.user_id==user.id,TournamentPrediction.provider==provider,TournamentPrediction.season==season));r=_out(p,deadline);r['provider']=provider;r['season']=season;return r
@router.put('/mine')
async def save(body:TournamentPredictionBody,provider:str='sstats',season:int=2026,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
 deadline=await _deadline(db,provider,season);now=datetime.now(timezone.utc)
 if now>=deadline:raise HTTPException(409,'Tournament prediction deadline has passed')
 values={k:getattr(body,k).strip() for k in ('winner','second_place','third_place','top_scorer','top_assistant','best_player')}
 if len({values['winner'].lower(),values['second_place'].lower(),values['third_place'].lower()})<3:raise HTTPException(422,'Winner, second and third place must be different teams')
 p=await db.scalar(select(TournamentPrediction).where(TournamentPrediction.user_id==user.id,TournamentPrediction.provider==provider,TournamentPrediction.season==season))
 if p is None:p=TournamentPrediction(user_id=user.id,provider=provider,season=season,deadline_at=deadline,**values);db.add(p)
 else:
  for k,v in values.items():setattr(p,k,v)
  p.deadline_at=deadline;p.updated_at=now
 await db.commit();await db.refresh(p);return _out(p,deadline)
