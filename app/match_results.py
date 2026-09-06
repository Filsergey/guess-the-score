import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.leagues import _eligible_final_matches, _membership, _oracle_score
from app.models import LeagueMember, Match, OraclePrediction, Prediction, User, UserLeague
from app.predictions import match_is_final, prediction_points

router = APIRouter(tags=["match-results"])


def _rank(rows: list[dict]) -> list[dict]:
    rows.sort(key=lambda x: (-x["points"], -x["exacts"], -x["outcomes"], -x["accuracy"], x["display_name"].casefold()))
    for index, row in enumerate(rows, 1): row["place"] = index
    return rows


async def _table(db: AsyncSession, league: UserLeague, exclude_match_id: int | None = None) -> list[dict]:
    members=(await db.execute(select(LeagueMember,User).join(User,User.id==LeagueMember.user_id).where(LeagueMember.league_id==league.id))).all();result=[]
    for member,u in members:
        eligible=await _eligible_final_matches(db,league,u)
        if exclude_match_id is not None: eligible=[m for m in eligible if m.id!=exclude_match_id]
        ids=[m.id for m in eligible];predictions=(await db.execute(select(Prediction).where(Prediction.user_id==u.id,Prediction.match_id.in_(ids)))).scalars().all() if ids else [];by_id={m.id:m for m in eligible};points=exacts=outcomes=submitted=0
        for p in predictions:
            pts=prediction_points(p,by_id.get(p.match_id)) if by_id.get(p.match_id) else None
            if pts is None: continue
            submitted+=1;points+=pts
            if pts==3: exacts+=1
            elif pts==1: outcomes+=1
        accuracy=round((exacts+outcomes)/submitted*100,1) if submitted else 0.0;result.append({"user_id":u.id,"display_name":u.display_name,"is_oracle":False,"points":points,"exacts":exacts,"outcomes":outcomes,"accuracy":accuracy})
    if league.include_oracle:
        eligible=await _eligible_final_matches(db,league)
        if exclude_match_id is not None: eligible=[m for m in eligible if m.id!=exclude_match_id]
        ids=[m.id for m in eligible];by_id={m.id:m for m in eligible};ops=(await db.execute(select(OraclePrediction).where(OraclePrediction.match_id.in_(ids)))).scalars().all() if ids else [];points=exacts=outcomes=submitted=0
        for op in ops:
            score=_oracle_score(op,by_id.get(op.match_id)) if by_id.get(op.match_id) else None
            if score is None: continue
            _,_,pts=score;submitted+=1;points+=pts
            if pts==3: exacts+=1
            elif pts==1: outcomes+=1
        accuracy=round((exacts+outcomes)/submitted*100,1) if submitted else 0.0;result.append({"user_id":None,"display_name":"Оракул","is_oracle":True,"points":points,"exacts":exacts,"outcomes":outcomes,"accuracy":accuracy})
    return _rank(result)


def _key(x): return "oracle" if x.get("is_oracle") else str(x.get("user_id"))

@router.get("/{league_id}/matches/{match_id}/summary")
async def final_match_summary(league_id:int,match_id:int,user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    league=await db.get(UserLeague,league_id)
    if league is None: raise HTTPException(404,"League not found")
    await _membership(league_id,user,db);match=await db.get(Match,match_id)
    if match is None: raise HTTPException(404,"Match not found")
    if match.provider!=league.tournament_provider or match.season!=league.tournament_season: raise HTTPException(409,"Match does not belong to this league tournament")
    if not match_is_final(match) or match.home_goals is None or match.away_goals is None: return {"final":False,"match_id":match_id,"league_id":league_id}
    members=(await db.execute(select(LeagueMember,User).join(User,User.id==LeagueMember.user_id).where(LeagueMember.league_id==league_id))).all();rows=[];mine=None
    for member,participant in members:
        eligible=match.kickoff_at>=participant.registered_at;prediction=await db.scalar(select(Prediction).where(Prediction.user_id==participant.id,Prediction.match_id==match_id)) if eligible else None;pts=prediction_points(prediction,match) if prediction else None
        item={"user_id":participant.id,"display_name":participant.display_name,"avatar_url":participant.avatar_url,"is_oracle":False,"eligible":eligible,"has_prediction":prediction is not None,"prediction":{"home_score":prediction.home_score,"away_score":prediction.away_score} if prediction else None,"points":pts if pts is not None else 0};rows.append(item)
        if participant.id==user.id: mine=item
    if league.include_oracle:
        op=await db.scalar(select(OraclePrediction).where(OraclePrediction.match_id==match_id));score=_oracle_score(op,match);ph=pa=pts=None
        if score is not None: ph,pa,pts=score
        rows.append({"user_id":None,"display_name":"Оракул","avatar_url":None,"is_oracle":True,"eligible":True,"has_prediction":score is not None,"prediction":{"home_score":ph,"away_score":pa} if score is not None else None,"points":pts or 0})
    valid=[x for x in rows if x["has_prediction"]];best=max((x["points"] for x in valid),default=0);winners=[x for x in valid if x["points"]==best];before=await _table(db,league,exclude_match_id=match_id);after=await _table(db,league);before_map={_key(x):x for x in before};after_map={_key(x):x for x in after}
    movement=[]
    for item in rows:
        k=_key(item);b=before_map.get(k);a=after_map.get(k);pb=b.get("place") if b else None;pa=a.get("place") if a else None;change=(pb-pa) if pb is not None and pa is not None else 0
        movement.append({**item,"place_before":pb,"place_after":pa,"place_change":change,"league_points_after":a.get("points",0) if a else 0})
    movement.sort(key=lambda x:(-x["points"],-x["place_change"],x["display_name"].casefold()))
    for i,x in enumerate(movement,1): x["match_place"]=i
    exact_hits=[x for x in movement if x["has_prediction"] and x["points"]==3];biggest_rise=max((x["place_change"] for x in movement),default=0);biggest_fall=min((x["place_change"] for x in movement),default=0)
    risers=[x for x in movement if biggest_rise>0 and x["place_change"]==biggest_rise];fallers=[x for x in movement if biggest_fall<0 and x["place_change"]==biggest_fall]
    mine_move=next((x for x in movement if not x["is_oracle"] and x["user_id"]==user.id),None);award="no_prediction"
    if mine and mine["has_prediction"]: award="exact" if mine["points"]==3 else "outcome" if mine["points"]==1 else "miss"
    compact=lambda xs:[{"user_id":x["user_id"],"display_name":x["display_name"],"is_oracle":x["is_oracle"],"points":x["points"],"place_change":x.get("place_change",0)} for x in xs]
    return {"final":True,"match_id":match_id,"league_id":league_id,"score":{"home":match.home_goals,"away":match.away_goals},"mine":mine,"award":award,"winners":compact(winners),"place_before":mine_move.get("place_before") if mine_move else None,"place_after":mine_move.get("place_after") if mine_move else None,"place_change":mine_move.get("place_change",0) if mine_move else 0,"league_points_after":mine_move.get("league_points_after",0) if mine_move else 0,"exact_hits":compact(exact_hits),"unique_exact":compact(exact_hits)[0] if len(exact_hits)==1 else None,"biggest_rise":biggest_rise,"risers":compact(risers),"biggest_fall":biggest_fall,"fallers":compact(fallers),"match_ranking":movement,"response":rows}
