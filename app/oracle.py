import math
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import Match

router = APIRouter(prefix="/api/oracle", tags=["oracle"])

def _num(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except (TypeError,ValueError): return None

def _prob(v):
    x=_num(v)
    if x is None:return None
    if x>1:x/=100
    return max(0.0,min(1.0,x))

def _score_from_xg(h,a):
    h=max(0.15,min(4.5,h));a=max(0.15,min(4.5,a))
    return min(6,max(0,int(math.floor(h+0.35)))),min(6,max(0,int(math.floor(a+0.35))))

@router.get('/matches/{match_id}')
async def oracle_prediction(match_id:int,db:AsyncSession=Depends(get_db)):
    match=await db.get(Match,match_id)
    if match is None:raise HTTPException(404,'Match not found')
    # Deterministic fallback: neutral 1:1. Rich SStats/Glicko data can override this in the UI endpoint later.
    home_score,away_score=1,1
    return {"match_id":match.id,"home_score":home_score,"away_score":away_score,"outcome":"draw","confidence":42,"data_quality":"low","source":"baseline","reasoning":"Базовый прогноз Оракула. Для этого матча пока недостаточно модельных данных, поэтому уверенность снижена.","key_factors":["Предматчевые модельные показатели пока недоступны","Прогноз будет уточняться по мере появления данных"],"failure_risks":["Составы и травмы могут изменить баланс","Ранний гол сильно меняет сценарий матча"]}
