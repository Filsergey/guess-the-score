from datetime import datetime, timezone
import re
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import get_current_user
from app.competitions.champions_league import classify_ucl_round
from app.database import get_db
from app.localization import team_name_ru
from app.models import Match, Player, Team, Tournament, TournamentPrediction, User
from app.providers.uefa import UEFAProvider

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

def _norm(value:str|None)->str:
 if not value:return ''
 text=value.casefold().replace('&',' and ').replace('’',"'")
 text=text.replace('ø','o').replace('ö','o').replace('ó','o').replace('ò','o').replace('ô','o').replace('ü','u').replace('ú','u').replace('ä','a').replace('á','a').replace('à','a').replace('é','e').replace('è','e').replace('í','i').replace('ñ','n').replace('ç','c')
 text=re.sub(r"[^\w\s']+",' ',text,flags=re.UNICODE)
 words=[x for x in text.split() if x not in {'fc','cf','afc','fk','sc','ac'}]
 aliases={'atletico madrid':'atleti','atletico de madrid':'atleti','club atletico de madrid':'atleti','bodo glimt':'bodo glimt','bodo/glimt':'bodo glimt','lask linz':'lask'}
 normalized=' '.join(words)
 return aliases.get(normalized,normalized)

def _norm_code(value:str|None)->str:
 code=re.sub(r'[^A-Z0-9]','',str(value or '').upper())
 aliases={'LAS':'LASK'}
 return aliases.get(code,code)

async def _is_ucl_scope(db:AsyncSession,provider:str,season:int,tournament_id:int|None)->bool:
 if provider!='sstats':return False
 if tournament_id is not None:
  tournament=await db.get(Tournament,tournament_id)
  return bool(tournament and int(tournament.provider_id or 0)==2)
 return season==2026

async def _main_stage_matches(db,provider,season,tournament_id:int|None=None):
 stmt=select(Match).where(Match.provider==provider,Match.season==season)
 if tournament_id is not None:stmt=stmt.where(Match.tournament_id==tournament_id)
 matches=(await db.execute(stmt.order_by(Match.kickoff_at))).scalars().all()
 if await _is_ucl_scope(db,provider,season,tournament_id):
  main=[]
  for m in matches:
   c=classify_ucl_round(season,m.kickoff_at)
   if c and c.get('stage') in {'league_phase','knockout'}:main.append(m)
  if main:return main
 return matches

async def _deadline(db,provider,season,tournament_id:int|None=None):
 matches=await _main_stage_matches(db,provider,season,tournament_id)
 if not matches:raise HTTPException(404,'Tournament matches not found')
 if await _is_ucl_scope(db,provider,season,tournament_id):
  md1=[]
  for m in matches:
   c=classify_ucl_round(season,m.kickoff_at) or {}
   if c.get('stage')=='league_phase' and c.get('matchday')==1:md1.append(m.kickoff_at)
  if md1:return min(md1)
 return matches[0].kickoff_at

def _player_out(player:Player|None):
 if not player:return None
 return {'id':player.id,'sstats_id':player.provider_id if player.provider=='sstats' else None,'name':player.display_name or player.name,'team':team_name_ru(player.team_name) if player.team_name else None,'team_original':player.team_name,'position':player.position,'number':player.shirt_number,'nationality':player.nationality,'photo':f'/api/players/{player.id}/photo' if (player.photo_data or player.photo_source_url) else None}

async def _out(db,p,deadline,tournament_id=None):
 now=datetime.now(timezone.utc);started=now>=deadline;locked=started and p is not None
 result={'provider':p.provider if p else None,'season':p.season if p else None,'tournament_id':p.tournament_id if p else tournament_id,'deadline_at':deadline,'started':started,'locked':locked,'can_save':not locked,'first_save_only':started and p is None,'prediction':None}
 if not p:return result
 ids=[x for x in (p.top_scorer_player_id,p.top_assistant_player_id,p.best_player_player_id) if x];players=(await db.execute(select(Player).where(Player.id.in_(ids)))).scalars().all() if ids else [];by_id={x.id:x for x in players}
 result['prediction']={'winner':p.winner,'second_place':p.second_place,'third_place':p.third_place,'top_scorer':p.top_scorer,'top_assistant':p.top_assistant,'best_player':p.best_player,'top_scorer_player_id':p.top_scorer_player_id,'top_assistant_player_id':p.top_assistant_player_id,'best_player_player_id':p.best_player_player_id,'top_scorer_player':_player_out(by_id.get(p.top_scorer_player_id)),'top_assistant_player':_player_out(by_id.get(p.top_assistant_player_id)),'best_player_player':_player_out(by_id.get(p.best_player_player_id)),'created_at':p.created_at,'updated_at':p.updated_at}
 return result

async def _competition_team_models(db,provider,season,tournament_id:int|None=None):
 matches=await _main_stage_matches(db,provider,season,tournament_id)
 ids={i for m in matches for i in (m.home_team_id,m.away_team_id) if i is not None}
 if not ids:return []
 teams=(await db.execute(select(Team).where(Team.id.in_(ids)).order_by(Team.name))).scalars().all()
 if provider!='sstats' or tournament_id is not None:return teams
 season_year=season+1 if season<2100 else season
 try:uefa_teams=await UEFAProvider().competition_teams(1,season_year)
 except Exception:return [t for t in teams if t.uefa_id is not None]
 by_name={};code_candidates={}
 for u in uefa_teams:
  candidates=[u.international_name,u.name_ru,u.name]
  candidates.extend(getattr(u,'aliases',()) or ())
  for candidate in candidates:
   key=_norm(candidate)
   if key:by_name[key]=u
  code=_norm_code(u.code)
  if code:code_candidates.setdefault(code,[]).append(u)
 by_code={code:rows[0] for code,rows in code_candidates.items() if len(rows)==1}
 eligible=[];changed=False
 for t in teams:
  u=None
  for candidate in (getattr(t,'source_name',None),t.name):
   key=_norm(candidate)
   if key and key in by_name:u=by_name[key];break
  if not u:
   code=_norm_code(t.code)
   if code:u=by_code.get(code)
  if not u:continue
  eligible.append(t)
  if t.uefa_id!=u.id:t.uefa_id=u.id;changed=True
  if u.name_ru and t.name!=u.name_ru:t.name=u.name_ru;changed=True
  if u.code and t.code!=str(u.code)[:20]:t.code=str(u.code)[:20];changed=True
  logo=u.logo_medium_url or u.logo_url or u.logo_big_url or u.logo_small_url
  if logo and t.logo_url!=logo:t.logo_url=logo;changed=True
 if changed:await db.commit()
 return eligible

async def _competition_teams(db,provider,season,tournament_id:int|None=None):
 teams=await _competition_team_models(db,provider,season,tournament_id)
 return [{'id':t.id,'provider_id':t.provider_id,'uefa_id':t.uefa_id,'name':t.name,'display_name':team_name_ru(t.name),'logo':f'/api/team-logo/db/{t.id}'} for t in teams]

@router.get('/mapping-status')
async def mapping_status(provider:str='sstats',season:int=2026,db:AsyncSession=Depends(get_db)):
 matches=await _main_stage_matches(db,provider,season)
 ids={i for m in matches for i in (m.home_team_id,m.away_team_id) if i is not None}
 sstats_teams=(await db.execute(select(Team).where(Team.id.in_(ids)).order_by(Team.name))).scalars().all() if ids else []
 matched=await _competition_team_models(db,provider,season)
 matched_ids={t.id for t in matched};matched_uefa_ids={t.uefa_id for t in matched if t.uefa_id is not None}
 season_year=season+1 if season<2100 else season
 try:uefa_teams=await UEFAProvider().competition_teams(1,season_year)
 except Exception as exc:raise HTTPException(502,f'UEFA mapping diagnostics failed: {type(exc).__name__}')
 unmatched_sstats=[{'sstats_id':t.provider_id,'name':t.name,'source_name':getattr(t,'source_name',None),'code':t.code} for t in sstats_teams if t.id not in matched_ids]
 unmatched_uefa=[{'uefa_id':u.id,'name':u.name_ru or u.name,'international_name':u.international_name,'code':u.code} for u in uefa_teams if u.id not in matched_uefa_ids]
 return {'competition':'UEFA Champions League','season':season,'uefa_season_year':season_year,'uefa_total':len(uefa_teams),'sstats_main_stage_total':len(sstats_teams),'matched':len(matched),'unmatched_sstats_count':len(unmatched_sstats),'unmatched_uefa_count':len(unmatched_uefa),'unmatched_sstats':unmatched_sstats,'unmatched_uefa':unmatched_uefa}

@router.get('/options/teams')
async def team_options(provider:str='sstats',season:int=2026,tournament_id:int|None=None,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
 del user;items=await _competition_teams(db,provider,season,tournament_id);items.sort(key=lambda x:x['display_name']);return {'count':len(items),'response':items}

@router.get('/options/players')
async def player_options(q:str|None=Query(default=None,max_length=80),provider:str='sstats',season:int=2026,tournament_id:int|None=None,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
 del user
 teams=await _competition_team_models(db,provider,season,tournament_id);team_provider_ids={t.provider_id for t in teams if t.provider=='sstats'}
 stmt=select(Player).where(Player.provider=='sstats',Player.is_active.is_(True))
 if team_provider_ids:stmt=stmt.where(Player.team_provider_id.in_(team_provider_ids))
 else:stmt=stmt.where(False)
 if q and q.strip():
  like=f"%{q.strip()}%";stmt=stmt.where(or_(Player.name.ilike(like),Player.display_name.ilike(like),Player.team_name.ilike(like)))
 stmt=stmt.order_by(Player.is_popular.desc(),Player.name).limit(40);rows=(await db.execute(stmt)).scalars().all();return {'count':len(rows),'response':[_player_out(x) for x in rows]}

@router.get('/mine')
async def mine(provider:str='sstats',season:int=2026,tournament_id:int|None=None,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
 deadline=await _deadline(db,provider,season,tournament_id);stmt=select(TournamentPrediction).where(TournamentPrediction.user_id==user.id,TournamentPrediction.provider==provider,TournamentPrediction.season==season)
 if tournament_id is not None:stmt=stmt.where(TournamentPrediction.tournament_id==tournament_id)
 else:stmt=stmt.where(TournamentPrediction.tournament_id.is_(None))
 p=await db.scalar(stmt);r=await _out(db,p,deadline,tournament_id);r['provider']=provider;r['season']=season;return r

async def _canonical_player(db:AsyncSession,player_id:int|None,submitted_name:str,provider:str,season:int,tournament_id:int|None=None)->Player:
 if not player_id:raise HTTPException(422,f'Выбери игрока «{submitted_name}» из списка')
 player=await db.get(Player,player_id)
 if not player or player.provider!='sstats' or not player.is_active:raise HTTPException(422,'Выбранный игрок отсутствует в актуальном каталоге SStats')
 teams=await _competition_team_models(db,provider,season,tournament_id);allowed_team_ids={t.provider_id for t in teams if t.provider=='sstats'}
 if player.team_provider_id not in allowed_team_ids:raise HTTPException(422,'Выбранный игрок не участвует в этом турнире')
 return player

@router.put('/mine')
async def save(body:TournamentPredictionBody,provider:str='sstats',season:int=2026,tournament_id:int|None=None,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
 if tournament_id is not None:
  tournament=await db.get(Tournament,tournament_id)
  if not tournament or tournament.provider!=provider:raise HTTPException(422,'Invalid tournament')
 deadline=await _deadline(db,provider,season,tournament_id);now=datetime.now(timezone.utc)
 stmt=select(TournamentPrediction).where(TournamentPrediction.user_id==user.id,TournamentPrediction.provider==provider,TournamentPrediction.season==season)
 if tournament_id is not None:stmt=stmt.where(TournamentPrediction.tournament_id==tournament_id)
 else:stmt=stmt.where(TournamentPrediction.tournament_id.is_(None))
 p=await db.scalar(stmt)
 if now>=deadline and p is not None:raise HTTPException(409,'Основной этап уже начался. Этот прогноз уже зафиксирован и больше не редактируется.')
 values={k:getattr(body,k).strip() for k in ('winner','second_place','third_place','top_scorer','top_assistant','best_player')};teams=await _competition_teams(db,provider,season,tournament_id);allowed={x['name'].casefold():x['name'] for x in teams}
 for k in ('winner','second_place','third_place'):
  canonical=allowed.get(values[k].casefold())
  if canonical is None:raise HTTPException(422,f'{values[k]} is not a team in this tournament')
  values[k]=canonical
 if len({values['winner'].casefold(),values['second_place'].casefold(),values['third_place'].casefold()})<3:raise HTTPException(422,'Winner, second and third place must be different teams')
 scorer=await _canonical_player(db,body.top_scorer_player_id,body.top_scorer,provider,season,tournament_id);assistant=await _canonical_player(db,body.top_assistant_player_id,body.top_assistant,provider,season,tournament_id);best=await _canonical_player(db,body.best_player_player_id,body.best_player,provider,season,tournament_id)
 values['top_scorer']=scorer.name;values['top_assistant']=assistant.name;values['best_player']=best.name;player_ids={'top_scorer_player_id':scorer.id,'top_assistant_player_id':assistant.id,'best_player_player_id':best.id}
 if p is None:p=TournamentPrediction(user_id=user.id,provider=provider,season=season,tournament_id=tournament_id,deadline_at=deadline,**values,**player_ids);db.add(p)
 else:
  for k,v in {**values,**player_ids}.items():setattr(p,k,v)
  p.tournament_id=tournament_id;p.deadline_at=deadline;p.updated_at=now
 await db.commit();await db.refresh(p);return await _out(db,p,deadline,tournament_id)