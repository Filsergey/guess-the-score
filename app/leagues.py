import json
import secrets
import string
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import LeagueMember, Match, OraclePrediction, Prediction, User, UserLeague
from app.predictions import prediction_points

router = APIRouter(prefix="/api/leagues", tags=["leagues"])

class LeagueCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    tournament_provider: str = Field(default="sstats", max_length=32)
    tournament_season: int = Field(default=2026, ge=2020, le=2100)
    is_private: bool = True
    include_oracle: bool = True
class LeagueJoin(BaseModel): invite_code: str = Field(min_length=4, max_length=12)

def _invite_code(length=8):
    alphabet=string.ascii_uppercase+string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))
def serialize_league(l,r,c): return {"id":l.id,"name":l.name,"invite_code":l.invite_code,"owner_user_id":l.owner_user_id,"member_role":r,"member_count":c,"tournament_provider":l.tournament_provider,"tournament_season":l.tournament_season,"is_private":l.is_private,"include_oracle":l.include_oracle,"created_at":l.created_at}
async def _unique_invite_code(db):
    for _ in range(10):
        code=_invite_code()
        if await db.scalar(select(UserLeague.id).where(UserLeague.invite_code==code)) is None:return code
    raise HTTPException(503,"Could not generate league invite code")
async def _membership(league_id,user,db):
    m=await db.scalar(select(LeagueMember).where(LeagueMember.league_id==league_id,LeagueMember.user_id==user.id))
    if m is None and user.role!="superadmin": raise HTTPException(403,"You are not a member of this league")
    return m

def _score_points(ph,pa,ah,aa):
    if ph==ah and pa==aa:return 3
    predicted=(ph>pa)-(ph<pa);actual=(ah>aa)-(ah<aa)
    return 1 if predicted==actual else 0

@router.get('/mine')
async def my_leagues(user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    sq=select(LeagueMember.league_id,func.count(LeagueMember.id).label('member_count')).group_by(LeagueMember.league_id).subquery()
    rows=(await db.execute(select(UserLeague,LeagueMember.role,sq.c.member_count).join(LeagueMember,LeagueMember.league_id==UserLeague.id).outerjoin(sq,sq.c.league_id==UserLeague.id).where(LeagueMember.user_id==user.id).order_by(UserLeague.created_at))).all()
    items=[serialize_league(l,r,int(c or 0)) for l,r,c in rows];return {'count':len(items),'response':items}
@router.post('')
async def create_league(body:LeagueCreate,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    name=body.name.strip()
    if len(name)<2:raise HTTPException(422,'League name is too short')
    now=datetime.now(timezone.utc);l=UserLeague(name=name,invite_code=await _unique_invite_code(db),owner_user_id=user.id,tournament_provider=body.tournament_provider,tournament_season=body.tournament_season,is_private=body.is_private,include_oracle=body.include_oracle,created_at=now);db.add(l);await db.flush();db.add(LeagueMember(league_id=l.id,user_id=user.id,role='owner',joined_at=now));await db.commit();await db.refresh(l);return serialize_league(l,'owner',1)
@router.post('/join')
async def join_league(body:LeagueJoin,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    l=await db.scalar(select(UserLeague).where(UserLeague.invite_code==body.invite_code.strip().upper()))
    if l is None:raise HTTPException(404,'League not found')
    m=await db.scalar(select(LeagueMember).where(LeagueMember.league_id==l.id,LeagueMember.user_id==user.id))
    if m is None:m=LeagueMember(league_id=l.id,user_id=user.id,role='member',joined_at=datetime.now(timezone.utc));db.add(m);await db.commit()
    c=await db.scalar(select(func.count(LeagueMember.id)).where(LeagueMember.league_id==l.id));return serialize_league(l,m.role,int(c or 0))
@router.get('/{league_id}/members')
async def league_members(league_id:int,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    membership=await _membership(league_id,user,db);l=await db.get(UserLeague,league_id)
    if l is None:raise HTTPException(404,'League not found')
    rows=(await db.execute(select(LeagueMember,User).join(User,User.id==LeagueMember.user_id).where(LeagueMember.league_id==league_id).order_by(LeagueMember.joined_at))).all()
    items=[{'user_id':m.user_id,'display_name':u.display_name,'username':u.username,'avatar_url':u.avatar_url,'role':m.role,'joined_at':m.joined_at} for m,u in rows]
    return {'league':serialize_league(l,membership.role if membership else 'superadmin',len(items)),'count':len(items),'response':items}

@router.get('/{league_id}/leaderboard')
async def leaderboard(league_id:int,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    membership=await _membership(league_id,user,db);league=await db.get(UserLeague,league_id)
    if league is None:raise HTTPException(404,'League not found')
    members=(await db.execute(select(LeagueMember,User).join(User,User.id==LeagueMember.user_id).where(LeagueMember.league_id==league_id))).all()
    result=[]
    for member,u in members:
        rows=(await db.execute(select(Prediction,Match).join(Match,Prediction.match_id==Match.id).where(Prediction.user_id==u.id,Match.provider==league.tournament_provider,Match.season==league.tournament_season,Match.kickoff_at>=u.registered_at))).all()
        points=outcomes=exacts=submitted=0
        for p,m in rows:
            if m.home_goals is None or m.away_goals is None:continue
            submitted+=1;pts=prediction_points(p,m) or 0;points+=pts
            if pts==3:exacts+=1
            elif pts==1:outcomes+=1
        correct=outcomes+exacts;accuracy=round(correct/submitted*100,1) if submitted else 0.0
        result.append({'user_id':u.id,'display_name':u.display_name,'username':u.username,'avatar_url':u.avatar_url,'member_role':member.role,'registered_at':u.registered_at,'points':points,'outcomes':outcomes,'exacts':exacts,'predictions':submitted,'accuracy':accuracy,'is_oracle':False})
    if league.include_oracle:
        oracle_rows=(await db.execute(select(OraclePrediction,Match).join(Match,OraclePrediction.match_id==Match.id).where(Match.provider==league.tournament_provider,Match.season==league.tournament_season))).all()
        points=outcomes=exacts=submitted=0
        for op,m in oracle_rows:
            if m.home_goals is None or m.away_goals is None:continue
            # Only predictions generated before kickoff are eligible. This prevents post-match generation from scoring.
            if op.generated_at is None or op.generated_at>=m.kickoff_at:continue
            try:
                data=json.loads(op.payload_json);ph=int(data['home_score']);pa=int(data['away_score'])
            except (ValueError,TypeError,KeyError,json.JSONDecodeError):continue
            submitted+=1;pts=_score_points(ph,pa,m.home_goals,m.away_goals);points+=pts
            if pts==3:exacts+=1
            elif pts==1:outcomes+=1
        correct=outcomes+exacts;accuracy=round(correct/submitted*100,1) if submitted else 0.0
        result.append({'user_id':None,'display_name':'Оракул','username':None,'avatar_url':None,'member_role':'oracle','registered_at':None,'points':points,'outcomes':outcomes,'exacts':exacts,'predictions':submitted,'accuracy':accuracy,'is_oracle':True})
    result.sort(key=lambda x:(-x['points'],-x['exacts'],-x['outcomes'],x['display_name'].lower()))
    for i,row in enumerate(result,1):row['place']=i
    return {'league':serialize_league(league,membership.role if membership else 'superadmin',len(members)),'count':len(result),'response':result}
