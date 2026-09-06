import json
import secrets
import string
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from app.auth import get_current_user
from app.database import get_db
from app.localization import round_name_ru, team_name_ru
from app.match_status import FINAL_MATCH_STATUSES, status_group, status_label_ru
from app.models import LeagueMember, Match, OraclePrediction, Prediction, Team, Tournament, User, UserLeague
from app.predictions import match_is_final, prediction_points
from app.tournament_logos import tournament_logo_url
router=APIRouter(prefix='/api/leagues',tags=['leagues'])
class LeagueCreate(BaseModel):
 name:str=Field(min_length=2,max_length=120);tournament_provider:str=Field(default='sstats',max_length=32);tournament_season:int=Field(default=2026,ge=2020,le=2100);tournament_id:int|None=None;is_private:bool=True;include_oracle:bool=True
class LeagueJoin(BaseModel):invite_code:str=Field(min_length=4,max_length=12)
class LeagueUpdate(BaseModel):name:str=Field(min_length=2,max_length=120)
def _invite_code(length=8):return ''.join(secrets.choice(string.ascii_uppercase+string.digits) for _ in range(length))
def serialize_league(l,r,c):return {'id':l.id,'name':l.name,'invite_code':l.invite_code,'owner_user_id':l.owner_user_id,'member_role':r,'member_count':c,'tournament_provider':l.tournament_provider,'tournament_season':l.tournament_season,'tournament_id':l.tournament_id,'is_private':l.is_private,'include_oracle':l.include_oracle,'created_at':l.created_at}
async def _unique_invite_code(db):
 for _ in range(10):
  code=_invite_code()
  if await db.scalar(select(UserLeague.id).where(UserLeague.invite_code==code)) is None:return code
 raise HTTPException(503,'Could not generate league invite code')
async def _membership(league_id,user,db):
 m=await db.scalar(select(LeagueMember).where(LeagueMember.league_id==league_id,LeagueMember.user_id==user.id))
 if m is None and user.role!='superadmin':raise HTTPException(403,'You are not a member of this league')
 return m
def _score_points(ph,pa,ah,aa):
 if ph==ah and pa==aa:return 3
 return 1 if (ph>pa)-(ph<pa)==(ah>aa)-(ah<aa) else 0
def _oracle_score(op,m):
 if not match_is_final(m) or m.home_goals is None or m.away_goals is None:return None
 if not op or op.generated_at is None or op.generated_at>=m.kickoff_at:return None
 try:data=json.loads(op.payload_json);ph=int(data['home_score']);pa=int(data['away_score'])
 except (ValueError,TypeError,KeyError,json.JSONDecodeError):return None
 return ph,pa,_score_points(ph,pa,m.home_goals,m.away_goals)
def _league_match_query(league):
 q=select(Match).where(Match.provider==league.tournament_provider,Match.season==league.tournament_season)
 if league.tournament_id is not None:q=q.where(Match.tournament_id==league.tournament_id)
 return q
async def _eligible_final_matches(db,league,user=None):
 q=_league_match_query(league).where(Match.status_short.in_(tuple(FINAL_MATCH_STATUSES)),Match.home_goals.is_not(None),Match.away_goals.is_not(None))
 if user is not None:q=q.where(Match.kickoff_at>=user.registered_at)
 return (await db.execute(q)).scalars().all()
@router.get('/tournaments')
async def league_tournaments(db:AsyncSession=Depends(get_db)):
 rows=(await db.execute(select(Tournament,Match.season,func.count(Match.id)).join(Match,Match.tournament_id==Tournament.id).where(Tournament.provider=='sstats',Match.provider=='sstats').group_by(Tournament.id,Match.season).order_by(Match.season.desc(),Tournament.name))).all()
 return {'count':len(rows),'response':[{'id':t.id,'provider':'sstats','provider_id':t.provider_id,'name':t.name,'country':t.country,'logo_url':tournament_logo_url(t.provider_id),'season':int(season),'match_count':int(count or 0)} for t,season,count in rows]}
@router.get('/mine')
async def my_leagues(user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
 sq=select(LeagueMember.league_id,func.count(LeagueMember.id).label('member_count')).group_by(LeagueMember.league_id).subquery();rows=(await db.execute(select(UserLeague,LeagueMember.role,sq.c.member_count).join(LeagueMember,LeagueMember.league_id==UserLeague.id).outerjoin(sq,sq.c.league_id==UserLeague.id).where(LeagueMember.user_id==user.id).order_by(UserLeague.created_at))).all();items=[serialize_league(l,r,int(c or 0)) for l,r,c in rows];return {'count':len(items),'response':items}
@router.post('')
async def create_league(body:LeagueCreate,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
 name=body.name.strip()
 if len(name)<2:raise HTTPException(422,'League name is too short')
 tournament=None
 if body.tournament_id is not None:
  tournament=await db.get(Tournament,body.tournament_id)
  if tournament is None or tournament.provider!='sstats':raise HTTPException(422,'Tournament is not available in SStats')
  exists=await db.scalar(select(func.count(Match.id)).where(Match.tournament_id==tournament.id,Match.provider=='sstats',Match.season==body.tournament_season))
  if not exists:raise HTTPException(422,'No SStats matches found for this tournament and season')
 now=datetime.now(timezone.utc);l=UserLeague(name=name,invite_code=await _unique_invite_code(db),owner_user_id=user.id,tournament_provider='sstats' if tournament else body.tournament_provider,tournament_season=body.tournament_season,tournament_id=tournament.id if tournament else None,is_private=body.is_private,include_oracle=body.include_oracle,created_at=now);db.add(l);await db.flush();db.add(LeagueMember(league_id=l.id,user_id=user.id,role='owner',joined_at=now));await db.commit();await db.refresh(l);return serialize_league(l,'owner',1)
@router.post('/join')
async def join_league(body:LeagueJoin,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
 l=await db.scalar(select(UserLeague).where(UserLeague.invite_code==body.invite_code.strip().upper()))
 if l is None:raise HTTPException(404,'League not found')
 m=await db.scalar(select(LeagueMember).where(LeagueMember.league_id==l.id,LeagueMember.user_id==user.id))
 if m is None:m=LeagueMember(league_id=l.id,user_id=user.id,role='member',joined_at=datetime.now(timezone.utc));db.add(m);await db.commit()
 c=await db.scalar(select(func.count(LeagueMember.id)).where(LeagueMember.league_id==l.id));return serialize_league(l,m.role,int(c or 0))
@router.patch('/{league_id}')
async def update_league(league_id:int,body:LeagueUpdate,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
 l=await db.get(UserLeague,league_id)
 if l is None:raise HTTPException(404,'League not found')
 if l.owner_user_id!=user.id and user.role!='superadmin':raise HTTPException(403,'Only the league owner can change it')
 name=body.name.strip()
 if len(name)<2:raise HTTPException(422,'League name is too short')
 l.name=name
 await db.commit();await db.refresh(l)
 c=await db.scalar(select(func.count(LeagueMember.id)).where(LeagueMember.league_id==league_id))
 role='owner' if l.owner_user_id==user.id else 'superadmin'
 return serialize_league(l,role,int(c or 0))
@router.delete('/{league_id}')
async def delete_league(league_id:int,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
 l=await db.get(UserLeague,league_id)
 if l is None:raise HTTPException(404,'League not found')
 if l.owner_user_id!=user.id and user.role!='superadmin':raise HTTPException(403,'Only the league owner can delete it')
 name=l.name
 await db.execute(delete(LeagueMember).where(LeagueMember.league_id==league_id))
 await db.delete(l)
 await db.commit()
 return {'ok':True,'id':league_id,'name':name}
@router.get('/{league_id}/members')
async def league_members(league_id:int,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
 membership=await _membership(league_id,user,db);l=await db.get(UserLeague,league_id)
 if l is None:raise HTTPException(404,'League not found')
 rows=(await db.execute(select(LeagueMember,User).join(User,User.id==LeagueMember.user_id).where(LeagueMember.league_id==league_id).order_by(LeagueMember.joined_at))).all();items=[{'user_id':m.user_id,'display_name':u.display_name,'username':u.username,'avatar_url':u.avatar_url,'role':m.role,'joined_at':m.joined_at} for m,u in rows];return {'league':serialize_league(l,membership.role if membership else 'superadmin',len(items)),'count':len(items),'response':items}
@router.get('/{league_id}/matches')
async def league_matches(league_id:int,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
 await _membership(league_id,user,db);league=await db.get(UserLeague,league_id)
 if league is None:raise HTTPException(404,'League not found')
 h,a=aliased(Team),aliased(Team);q=select(Match,h,a).join(h,Match.home_team_id==h.id).join(a,Match.away_team_id==a.id).where(Match.provider==league.tournament_provider,Match.season==league.tournament_season)
 if league.tournament_id is not None:q=q.where(Match.tournament_id==league.tournament_id)
 rows=(await db.execute(q.order_by(Match.kickoff_at))).all()
 items=[]
 for m,home,away in rows:
  items.append({'id':m.id,'provider':m.provider,'provider_id':m.provider_id,'season':m.season,'tournament_id':m.tournament_id,'round':round_name_ru(m.round_name),'kickoff_at':m.kickoff_at,'status':m.status_short,'status_source':m.status_long,'status_group':status_group(m.status_short),'status_label':status_label_ru(m.status_short),'elapsed':m.elapsed,'home':{'id':home.id,'provider':home.provider,'provider_id':home.provider_id,'name':team_name_ru(home.name),'name_original':home.name,'code':home.code,'logo':f'/api/team-logo/db/{home.id}','goals':m.home_goals},'away':{'id':away.id,'provider':away.provider,'provider_id':away.provider_id,'name':team_name_ru(away.name),'name_original':away.name,'code':away.code,'logo':f'/api/team-logo/db/{away.id}','goals':m.away_goals}})
 return {'league':serialize_league(league,'member',0),'count':len(items),'response':items}
@router.get('/{league_id}/leaderboard')
async def leaderboard(league_id:int,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
 membership=await _membership(league_id,user,db);league=await db.get(UserLeague,league_id)
 if league is None:raise HTTPException(404,'League not found')
 members=(await db.execute(select(LeagueMember,User).join(User,User.id==LeagueMember.user_id).where(LeagueMember.league_id==league_id))).all();result=[]
 for member,u in members:
  eligible=await _eligible_final_matches(db,league,u);eligible_ids=[m.id for m in eligible];preds=(await db.execute(select(Prediction).where(Prediction.user_id==u.id,Prediction.match_id.in_(eligible_ids)))).scalars().all() if eligible_ids else [];match_by_id={m.id:m for m in eligible};points=outcomes=exacts=submitted=0
  for p in preds:
   m=match_by_id.get(p.match_id);pts=prediction_points(p,m) if m else None
   if pts is None:continue
   submitted+=1;points+=pts;exacts+=pts==3;outcomes+=pts==1
  accuracy=round((outcomes+exacts)/submitted*100,1) if submitted else 0.;result.append({'user_id':u.id,'display_name':u.display_name,'username':u.username,'avatar_url':u.avatar_url,'member_role':member.role,'registered_at':u.registered_at,'points':points,'outcomes':outcomes,'exacts':exacts,'predictions':submitted,'eligible_completed_matches':len(eligible),'missed':max(0,len(eligible)-submitted),'accuracy':accuracy,'is_oracle':False})
 if league.include_oracle:
  eligible=await _eligible_final_matches(db,league);ids=[m.id for m in eligible];by={m.id:m for m in eligible};ops=(await db.execute(select(OraclePrediction).where(OraclePrediction.match_id.in_(ids)))).scalars().all() if ids else [];points=outcomes=exacts=submitted=0
  for op in ops:
   score=_oracle_score(op,by.get(op.match_id)) if by.get(op.match_id) else None
   if score is None:continue
   pts=score[2];submitted+=1;points+=pts;exacts+=pts==3;outcomes+=pts==1
  accuracy=round((outcomes+exacts)/submitted*100,1) if submitted else 0.;result.append({'user_id':None,'display_name':'Оракул','username':None,'avatar_url':None,'member_role':'oracle','registered_at':None,'points':points,'outcomes':outcomes,'exacts':exacts,'predictions':submitted,'eligible_completed_matches':len(eligible),'missed':max(0,len(eligible)-submitted),'accuracy':accuracy,'is_oracle':True})
 result.sort(key=lambda x:(-x['points'],-x['exacts'],-x['outcomes'],-x['accuracy'],x['display_name'].lower()))
 for i,row in enumerate(result,1):row['place']=i
 return {'league':serialize_league(league,membership.role if membership else 'superadmin',len(members)),'count':len(result),'response':result}
@router.get('/{league_id}/participants/{participant}/history')
async def participant_history(league_id:int,participant:str,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
 membership=await _membership(league_id,user,db);league=await db.get(UserLeague,league_id)
 if league is None:raise HTTPException(404,'League not found')
 is_oracle=participant.lower()=='oracle';target=None
 if is_oracle:
  if not league.include_oracle:raise HTTPException(404,'Oracle is not enabled in this league')
 else:
  try:user_id=int(participant)
  except ValueError:raise HTTPException(422,'Invalid participant')
  member=(await db.execute(select(LeagueMember,User).join(User,User.id==LeagueMember.user_id).where(LeagueMember.league_id==league_id,LeagueMember.user_id==user_id))).first()
  if member is None:raise HTTPException(404,'Participant is not a member of this league')
  _,target=member
 h,a=aliased(Team),aliased(Team);q=select(Match,h,a).join(h,Match.home_team_id==h.id).join(a,Match.away_team_id==a.id).where(Match.provider==league.tournament_provider,Match.season==league.tournament_season,Match.status_short.in_(tuple(FINAL_MATCH_STATUSES)),Match.home_goals.is_not(None),Match.away_goals.is_not(None))
 if league.tournament_id is not None:q=q.where(Match.tournament_id==league.tournament_id)
 if target is not None:q=q.where(Match.kickoff_at>=target.registered_at)
 matches=(await db.execute(q.order_by(Match.kickoff_at.desc()))).all();match_ids=[m.id for m,_,_ in matches]
 if is_oracle:preds=(await db.execute(select(OraclePrediction).where(OraclePrediction.match_id.in_(match_ids)))).scalars().all() if match_ids else []
 else:preds=(await db.execute(select(Prediction).where(Prediction.user_id==target.id,Prediction.match_id.in_(match_ids)))).scalars().all() if match_ids else []
 pred_by_match={p.match_id:p for p in preds};items=[];points=outcomes=exacts=submitted=0
 for m,home,away in matches:
  p=pred_by_match.get(m.id);ph=pa=pts=None
  if is_oracle:
   score=_oracle_score(p,m)
   if score is not None:ph,pa,pts=score
  elif p is not None:ph,pa=p.home_score,p.away_score;pts=prediction_points(p,m)
  if pts is not None:submitted+=1;points+=pts;exacts+=pts==3;outcomes+=pts==1
  items.append({'match_id':m.id,'kickoff_at':m.kickoff_at,'round':round_name_ru(m.round_name),'home':{'id':home.id,'name':team_name_ru(home.name),'logo':f'/api/team-logo/db/{home.id}','goals':m.home_goals},'away':{'id':away.id,'name':team_name_ru(away.name),'logo':f'/api/team-logo/db/{away.id}','goals':m.away_goals},'prediction':{'home_score':ph,'away_score':pa} if pts is not None else None,'points':pts or 0,'submitted':pts is not None})
 accuracy=round((outcomes+exacts)/submitted*100,1) if submitted else 0.;missed=max(0,len(items)-submitted);participant_data={'user_id':None,'display_name':'Оракул','avatar_url':None,'is_oracle':True} if is_oracle else {'user_id':target.id,'display_name':target.display_name,'avatar_url':target.avatar_url,'is_oracle':False,'registered_at':target.registered_at};return {'league':{'id':league.id,'name':league.name},'participant':participant_data,'summary':{'points':points,'outcomes':outcomes,'exacts':exacts,'predictions':submitted,'accuracy':accuracy,'eligible_completed_matches':len(items),'missed':missed},'count':len(items),'response':items}
# Mounted after helper definitions to avoid circular imports during module initialization.
from app.match_results import router as match_results_router
from app.achievements import router as achievements_router
router.include_router(match_results_router)
router.include_router(achievements_router)
