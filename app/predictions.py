import base64
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.match_status import is_final_status, is_live_status
from app.models import LeagueMember, Match, OraclePrediction, Prediction, User, UserLeague
from app.profile_models import UserProfile

router = APIRouter(prefix="/api/predictions", tags=["predictions"])
ORACLE_STYLES={"merciless","irony","calm","numbers"}

class PredictionInput(BaseModel):
    home_score: int = Field(ge=0, le=30)
    away_score: int = Field(ge=0, le=30)

class ProfileUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    avatar_data_url: str | None = Field(default=None, max_length=2500000)
    oracle_style: str | None = Field(default=None, max_length=32)

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

def _custom_avatar_url(user_id:int)->str:return f"/api/predictions/profile/avatar/{user_id}"

def _profile_response(user:User,profile:UserProfile|None=None)->dict:
    return {"id":user.id,"telegram_id":user.telegram_id,"username":user.username,"display_name":user.display_name,"avatar_url":user.avatar_url,"role":user.role,"registered_at":user.registered_at,"last_login_at":user.last_login_at,"oracle_style":profile.oracle_style if profile and profile.oracle_style in ORACLE_STYLES else "irony"}

async def _apply_custom_profile(user:User,db:AsyncSession)->User:
    profile=await db.scalar(select(UserProfile).where(UserProfile.user_id==user.id))
    if profile is None:return user
    changed=False
    if profile.display_name and user.display_name!=profile.display_name:user.display_name=profile.display_name;changed=True
    if profile.avatar_data:
        avatar_url=_custom_avatar_url(user.id)
        if user.avatar_url!=avatar_url:user.avatar_url=avatar_url;changed=True
    if changed:await db.commit();await db.refresh(user)
    return user

def _decode_avatar(data_url:str)->tuple[bytes,str]:
    allowed={"image/jpeg","image/png","image/webp"}
    try:
        header,payload=data_url.split(",",1)
        media_type=header.removeprefix("data:").split(";",1)[0].lower()
        if media_type not in allowed or ";base64" not in header.lower():raise ValueError
        raw=base64.b64decode(payload,validate=True)
    except Exception as exc:
        raise HTTPException(422,"Некорректный файл аватарки") from exc
    if len(raw)<100:raise HTTPException(422,"Файл аватарки пустой")
    if len(raw)>1500000:raise HTTPException(413,"Аватарка слишком большая")
    return raw,media_type

@router.get("/profile/me")
async def profile_me(user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db))->dict:
    user=await _apply_custom_profile(user,db);profile=await db.scalar(select(UserProfile).where(UserProfile.user_id==user.id));return _profile_response(user,profile)

@router.patch("/profile/me")
async def update_profile(body:ProfileUpdate,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db))->dict:
    name=body.display_name.strip()
    if len(name)<2:raise HTTPException(422,"Имя должно быть не короче 2 символов")
    profile=await db.scalar(select(UserProfile).where(UserProfile.user_id==user.id))
    if profile is None:profile=UserProfile(user_id=user.id);db.add(profile)
    profile.display_name=name;user.display_name=name
    if body.oracle_style is not None:
        style=body.oracle_style.strip().lower()
        if style not in ORACLE_STYLES:raise HTTPException(422,"Неизвестный стиль Оракула")
        profile.oracle_style=style
    elif not profile.oracle_style:
        profile.oracle_style="irony"
    if body.avatar_data_url is not None:
        raw,media_type=_decode_avatar(body.avatar_data_url)
        profile.avatar_data=raw;profile.avatar_media_type=media_type;user.avatar_url=_custom_avatar_url(user.id)
    profile.updated_at=datetime.now(timezone.utc)
    await db.commit();await db.refresh(user);await db.refresh(profile)
    return _profile_response(user,profile)

@router.get("/profile/avatar/{user_id}")
async def profile_avatar(user_id:int,db:AsyncSession=Depends(get_db)):
    profile=await db.scalar(select(UserProfile).where(UserProfile.user_id==user_id))
    if profile is None or not profile.avatar_data:raise HTTPException(404,"Avatar not found")
    return Response(content=profile.avatar_data,media_type=profile.avatar_media_type or "image/jpeg",headers={"Cache-Control":"no-store, max-age=0"})

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
    league=None;human_members=0
    if league_id is not None:
        league=await db.get(UserLeague,league_id)
        if league is None:raise HTTPException(404,"League not found")
        membership=await db.scalar(select(LeagueMember).where(LeagueMember.league_id==league_id,LeagueMember.user_id==user.id))
        if membership is None and user.role!="superadmin":raise HTTPException(403,"You are not a member of this league")
        if match.provider!=league.tournament_provider or match.season!=league.tournament_season:raise HTTPException(409,"Match does not belong to this league tournament")
        rows=(await db.execute(select(LeagueMember,User,Prediction).join(User,User.id==LeagueMember.user_id).outerjoin(Prediction,and_(Prediction.user_id==User.id,Prediction.match_id==match_id)).where(LeagueMember.league_id==league_id).order_by(User.display_name))).all();human_members=len(rows)
    else:
        rows=[(None,u,p) for p,u in (await db.execute(select(Prediction,User).join(User,Prediction.user_id==User.id).where(Prediction.match_id==match_id).order_by(User.display_name))).all()];human_members=len(rows)
    response=[];submitted=0
    for member,participant,prediction in rows:
        mine=participant.id==user.id;has=prediction is not None;submitted+=int(has)
        item={"user_id":participant.id,"display_name":participant.display_name,"username":participant.username,"avatar_url":participant.avatar_url,"has_prediction":has,"is_mine":mine,"is_oracle":False,"member_role":member.role if member else None}
        if has and started:
            pts=prediction_points(prediction,match) if final else None;live_pts=score_points(prediction.home_score,prediction.away_score,match.home_goals,match.away_goals) if live else None
            item["prediction"]={"home_score":prediction.home_score,"away_score":prediction.away_score,"points":pts,"live_points":live_pts}
        response.append(item)
    oracle_included=False
    if league and league.include_oracle:
        oracle_included=True;op=await db.scalar(select(OraclePrediction).where(OraclePrediction.match_id==match_id));oracle_prediction=None;oracle_has_prediction=False
        if op and op.generated_at and op.generated_at<match.kickoff_at:
            try:
                payload=json.loads(op.payload_json);ph=int(payload["home_score"]);pa=int(payload["away_score"]);oracle_has_prediction=True
                if started:oracle_prediction={"home_score":ph,"away_score":pa,"points":score_points(ph,pa,match.home_goals,match.away_goals) if final else None,"live_points":score_points(ph,pa,match.home_goals,match.away_goals) if live else None}
            except (ValueError,TypeError,KeyError,json.JSONDecodeError):pass
        response.append({"user_id":None,"display_name":"Оракул","username":None,"avatar_url":None,"has_prediction":oracle_has_prediction,"is_mine":False,"is_oracle":True,"member_role":"oracle","prediction":oracle_prediction})
    if live or final:
        key="live_points" if live else "points"
        response.sort(key=lambda x:(-(x.get("prediction") or {}).get(key,-1),not x.get("has_prediction"),(x.get("display_name") or "").casefold()))
        rank=0;last_points=None
        for index,item in enumerate(response,1):
            pts=(item.get("prediction") or {}).get(key)
            if pts is None:item["match_rank"]=None;continue
            if pts!=last_points:rank=index;last_points=pts
            item["match_rank"]=rank
    leaders=[]
    if live:
        valid=[x for x in response if (x.get("prediction") or {}).get("live_points") is not None]
        if valid:
            best=max((x["prediction"]["live_points"] for x in valid),default=0);leaders=[{"user_id":x.get("user_id"),"display_name":x.get("display_name"),"is_oracle":x.get("is_oracle",False),"live_points":best} for x in valid if x["prediction"]["live_points"]==best]
    return {"match_id":match_id,"league_id":league_id,"started":started,"live":live,"final":final,"predictions_visible":started,"human_member_count":human_members,"participant_count":len(response),"submitted_count":submitted,"oracle_included":oracle_included,"score":{"home":match.home_goals,"away":match.away_goals} if (live or final) else None,"leaders":leaders,"response":response}

@router.get("/mine")
async def my_predictions(user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db))->dict:
    rows=(await db.execute(select(Prediction,Match).join(Match,Prediction.match_id==Match.id).where(Prediction.user_id==user.id).order_by(Match.kickoff_at))).all();items=[serialize_prediction(p,m) for p,m in rows];return {"count":len(items),"response":items}
