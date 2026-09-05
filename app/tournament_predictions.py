from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import get_current_user
from app.competitions.champions_league import classify_ucl_round
from app.database import get_db
from app.localization import team_name_ru
from app.models import Match, Player, Team, TournamentPrediction, User

router=APIRouter(prefix='/api/tournament-predictions',tags=['tournament-predictions'])

class TournamentPredictionBody(BaseModel):
 winner:str=Field(min_length=1,max_length=150)
 second_place:str=Field(min_length=1,max_length=150)
 third_place:str=Field(min_length=1,max_length=150)
 top_scorer:str=Field(min_length=1,max_length=150)
 top_assistant:str=Field(min_length=1,max_length=150)
 best_player:str=Field(min_length=1,max_length=150)
 top_scorer_player_id:int|None=None
 top_assistant_player_id:int|None=None
 best_player_player_id:int|None=None

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

def _player_out(player:Player|None):
 if not player:return None
 return {'id':player.id,'sstats_id':player.provider_id if player.provider=='sstats' else None,'name':player.display_name or player.name,'team':team_name_ru(player.team_name) if player.team_name else None,'team_original':player.team_name,'position':player.position,'number':player.shirt_number,'nationality':player.nationality,'photo':f'/api/players/{player.id}/photo' if (player.photo_data or player.photo_source_url) else None}

async def _out(db,p,deadline):
 now=datetime.now(timezone.utc);result={'provider':p.provider if p else None,'season':p.season if p else None,'deadline_at':deadline,'locked':now>=deadline,'prediction':None}
 if not p:return result
 ids=[x for x in (p.top_scorer_player_id,p.top_assistant_player_id,p.best_player_player_id) if x];players=(await db.execute(select(Player).where(Player.id.in_(ids)))).scalars().all() if ids else [];by_id={x.id:x for x in players}
 result['prediction']={'winner':p.winner,'second_place':p.second_place,'third_place':p.third_place,'top_scorer':p.top_scorer,'top_assistant':p.top_assistant,'best_player':p.best_player,'top_scorer_player_id':p.top_scorer_player_id,'top_assistant_player_id':p.top_assistant_player_id,'best_player_player_id':p.best_player_player_id,'top_scorer_player':_player_out(by_id.get(p.top_scorer_player_id)),'top_assistant_player':_player_out(by_id.get(p.top_assistant_player_id)),'best_player_player':_player_out(by_id.get(p.best_player_player_id)),'created_at':p.created_at,'updated_at':p.updated_at}
 return result

async def _competition_teams(db,provider,season):
 matches=await _main_stage_matches(db,provider,season);ids={i for m in matches for i in (m.home_team_id,m.away_team_id) if i is not None}
 if not ids:return []
 teams=(await db.execute(select(Team).where(Team.id.in_(ids)).order_by(Team.name))).scalars().all();return [{'id':t.id,'provider_id':t.provider_id,'name':t.name,'display_name':team_name_ru(t.name),'logo':f'/api/team-logo/db/{t.id}'} for t in teams]

@router.get('/options/teams')
async def team_options(provider:str='sstats',season:int=2026,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
 del user;items=await _competition_teams(db,provider,season);items.sort(key=lambda x:x['display_name']);return {'count':len(items),'response':items}

@router.get('/options/players')
async def player_options(q:str|None=Query(default=None,max_length=80),provider:str='sstats',season:int=2026,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
 del user,provider,season
 stmt=select(Player).where(Player.provider=='sstats',Player.is_active.is_(True))
 if q and q.strip():
  like=f"%{q.strip()}%";stmt=stmt.where(or_(Player.name.ilike(like),Player.display_name.ilike(like),Player.team_name.ilike(like)))
 stmt=stmt.order_by(Player.is_popular.desc(),Player.name).limit(40);rows=(await db.execute(stmt)).scalars().all();return {'count':len(rows),'response':[_player_out(x) for x in rows]}

@router.get('/mine')
async def mine(provider:str='sstats',season:int=2026,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
 deadline=await _deadline(db,provider,season);p=await db.scalar(select(TournamentPrediction).where(TournamentPrediction.user_id==user.id,TournamentPrediction.provider==provider,TournamentPrediction.season==season));r=await _out(db,p,deadline);r['provider']=provider;r['season']=season;return r

async def _canonical_player(db:AsyncSession,player_id:int|None,submitted_name:str)->Player:
 if not player_id:raise HTTPException(422,f'Выбери игрока «{submitted_name}» из списка')
 player=await db.get(Player,player_id)
 if not player or player.provider!='sstats' or not player.is_active:raise HTTPException(422,'Выбранный игрок отсутствует в актуальном каталоге SStats')
 return player

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
 scorer=await _canonical_player(db,body.top_scorer_player_id,body.top_scorer);assistant=await _canonical_player(db,body.top_assistant_player_id,body.top_assistant);best=await _canonical_player(db,body.best_player_player_id,body.best_player)
 values['top_scorer']=scorer.name;values['top_assistant']=assistant.name;values['best_player']=best.name;player_ids={'top_scorer_player_id':scorer.id,'top_assistant_player_id':assistant.id,'best_player_player_id':best.id}
 p=await db.scalar(select(TournamentPrediction).where(TournamentPrediction.user_id==user.id,TournamentPrediction.provider==provider,TournamentPrediction.season==season))
 if p is None:p=TournamentPrediction(user_id=user.id,provider=provider,season=season,deadline_at=deadline,**values,**player_ids);db.add(p)
 else:
  for k,v in {**values,**player_ids}.items():setattr(p,k,v)
  p.deadline_at=deadline;p.updated_at=now
 await db.commit();await db.refresh(p);return await _out(db,p,deadline)
