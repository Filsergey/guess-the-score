import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.match_status import is_final_status, is_live_status
from app.models import LeagueMember, Match, OraclePrediction, Prediction, User, UserLeague

router = APIRouter(prefix="/api/predictions", tags=["predictions"])

class PredictionInput(BaseModel):
    home_score: int = Field(ge=0, le=30)
    away_score: int = Field(ge=0, le=30)

def _outcome(home:int,away:int)->int:return 1 if home>away else -1 if home<away else 0

def score_points(home_score:int,away_score:int,actual_home:int|None,actual_away:int|None)->int|None:
    if actual_home is None or actual_away is None:return None
    if home_score==actual_home and away_score==actual_away:return 3
    return 1 if _outcome(home_score,away_score)==_outcome(actual_home,actual_away) else 0

def match_is_final(match:Match)->bool:return is_final_status(match.status_short)

def prediction_points(prediction:Prediction,match:Match)->int|None:
    if not match_is_final(match):return None
    return score_points(prediction.home_score,prediction.away_score,match.home_goals,match.away_goals)

def serialize_prediction(prediction:Prediction,match:Match)->dict:
    return {"id":prediction.id,"match_id":prediction.match_id,"home_score":prediction.home_score,"away_score":prediction.away_score,"created_at":prediction.created_at,"updated_at":prediction.updated_at,"locked":datetime.now(timezone.utc)>=match.kickoff_at,"points":prediction_points(prediction,match)}

@router.put("/matches/{match_id}")
async def save_prediction(match_id:int,body:PredictionInput,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db))->dict:
    match=await db.get(Match,match_id)
    if match is None:raise HTTPException(404,"Match not found")
    now=datetime.now(timezone.utc)
    if now>=match.kickoff_at:raise HTTPException(409,"Prediction is locked because the match has started")
    if match.kickoff_at<user.registered_at:raise HTTPException(409,"Match is not eligible for this user")
    prediction=await db.scalar(select(Prediction).where(Prediction.user_id==user.id,Prediction.match_id==match_id))
    if prediction is None:prediction=Prediction(user_id=user.id,match_id=match_id,home_score=body.home_score,away_score=body.away_score,created_at=now,updated_at=now);db.add(prediction)
    else:prediction.home_score=body.home_score;prediction.away_score=body.away_score;prediction.updated_at=now
    await db.commit();await db.refresh(prediction);return serialize_prediction(prediction,match)

@router.get("/matches/{match_id}/mine")
async def my_prediction(match_id:int,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db))->dict:
    match=await db.get(Match,match_id)
    if match is None:raise HTTPException(404,"Match not found")
    prediction=await db.scalar(select(Prediction).where(Prediction.user_id==user.id,Prediction.match_id==match_id))
    return {"match_id":match_id,"has_prediction":prediction is not None,"prediction":serialize_prediction(prediction,match) if prediction else None}

@router.get("/matches/{match_id}/participants")
async def match_prediction_participants(match_id:int,league_id:int|None=Query(default=None,ge=1),user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db))->dict:
    match=await db.get(Match,match_id)
    if match is None:raise HTTPException(404,"Match not found")
    started=datetime.now(timezone.utc)>=match.kickoff_at;live=is_live_status(match.status_short);final=match_is_final(match)
    league=None
    if league_id is not None:
        league=await db.get(UserLeague,league_id)
        if league is None:raise HTTPException(404,"League not found")
        membership=await db.scalar(select(LeagueMember).where(LeagueMember.league_id==league_id,LeagueMember.user_id==user.id))
        if membership is None and user.role!="superadmin":raise HTTPException(403,"You are not a member of this league")
        if match.provider!=league.tournament_provider or match.season!=league.tournament_season:raise HTTPException(409,"Match does not belong to this league tournament")
        rows=(await db.execute(select(LeagueMember,User,Prediction).join(User,User.id==LeagueMember.user_id).outerjoin(Prediction,and_(Prediction.user_id==User.id,Prediction.match_id==match_id)).where(LeagueMember.league_id==league_id).order_by(User.display_name))).all()
    else:
        # Compatibility mode for clients that have no league selected yet.
        rows=[(None,u,p) for p,u in (await db.execute(select(Prediction,User).join(User,Prediction.user_id==User.id).where(Prediction.match_id==match_id).order_by(User.display_name))).all()]
    response=[];submitted=0
    for member,participant,prediction in rows:
        mine=participant.id==user.id;has=prediction is not None;submitted+=int(has)
        item={"user_id":participant.id,"display_name":participant.display_name,"username":participant.username,"avatar_url":participant.avatar_url,"has_prediction":has,"is_mine":mine,"is_oracle":False,"member_role":member.role if member else None}
        if has and (started or mine):
            pts=prediction_points(prediction,match) if final else None;live_pts=score_points(prediction.home_score,prediction.away_score,match.home_goals,match.away_goals) if live else None
            item["prediction"]={"home_score":prediction.home_score,"away_score":prediction.away_score,"points":pts,"live_points":live_pts}
        response.append(item)
    if league and league.include_oracle:
        op=await db.scalar(select(OraclePrediction).where(OraclePrediction.match_id==match_id));prediction=None
        if op and op.generated_at and op.generated_at<match.kickoff_at:
            try:
                payload=json.loads(op.payload_json);ph=int(payload["home_score"]);pa=int(payload["away_score"]);prediction={"home_score":ph,"away_score":pa,"points":score_points(ph,pa,match.home_goals,match.away_goals) if final else None,"live_points":score_points(ph,pa,match.home_goals,match.away_goals) if live else None}
            except (ValueError,TypeError,KeyError,json.JSONDecodeError):pass
        response.append({"user_id":None,"display_name":"Оракул","username":None,"avatar_url":None,"has_prediction":prediction is not None,"is_mine":False,"is_oracle":True,"member_role":"oracle","prediction":prediction})
    return {"match_id":match_id,"league_id":league_id,"started":started,"live":live,"final":final,"predictions_visible":started,"member_count":len(response),"submitted_count":submitted,"score":{"home":match.home_goals,"away":match.away_goals} if (live or final) else None,"response":response}

@router.get("/mine")
async def my_predictions(user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db))->dict:
    rows=(await db.execute(select(Prediction,Match).join(Match,Prediction.match_id==Match.id).where(Prediction.user_id==user.id).order_by(Match.kickoff_at))).all();items=[serialize_prediction(p,m) for p,m in rows];return {"count":len(items),"response":items}
