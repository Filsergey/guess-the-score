import math
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models import Match
from app.providers.sstats import SStatsProvider

router=APIRouter(prefix="/api/oracle",tags=["oracle"])
def _num(v):
    try:
        x=float(v);return x if math.isfinite(x) else None
    except (TypeError,ValueError):return None
def _prob(v):
    x=_num(v)
    if x is None:return None
    if x>1:x/=100
    return max(0.0,min(1.0,x))
def _first(payload):
    data=payload.get('data') or payload.get('response') or []
    return data[0] if isinstance(data,list) and data else (data if isinstance(data,dict) else {})
def _v(d,name):
    camel=name[:1].lower()+name[1:];return d.get(camel,d.get(name))
def _score(h,a):
    h=max(.15,min(4.5,h));a=max(.15,min(4.5,a))
    return min(6,max(0,int(math.floor(h+.35)))),min(6,max(0,int(math.floor(a+.35))))
def _odds_probs(h,d,a):
    vals=[_num(h),_num(d),_num(a)]
    if not all(x and x>1 for x in vals):return None
    inv=[1/x for x in vals];s=sum(inv);return [x/s for x in inv]

@router.get('/matches/{match_id}')
async def oracle_prediction(match_id:int,db:AsyncSession=Depends(get_db)):
    match=await db.get(Match,match_id)
    if match is None:raise HTTPException(404,'Match not found')
    details={};glicko={};errors=[]
    if match.provider=='sstats':
        p=SStatsProvider()
        try:details=_first(await p.query_game_details(match.provider_id))
        except Exception as e:errors.append(f'details:{type(e).__name__}')
        try:glicko=_first(await p.get_glicko(match.provider_id))
        except Exception as e:errors.append(f'glicko:{type(e).__name__}')
    hx=_num(_v(details,'GlickoXgHome')) or _num(_v(glicko,'XgHome')) or _num(_v(details,'OddsXgHome'))
    ax=_num(_v(details,'GlickoXgAway')) or _num(_v(glicko,'XgAway')) or _num(_v(details,'OddsXgAway'))
    hp=_prob(_v(details,'GlickoWinProbHome')) or _prob(_v(glicko,'WinProbHome'))
    ap=_prob(_v(details,'GlickoWinProbAway')) or _prob(_v(glicko,'WinProbAway'))
    odds=_odds_probs(_v(details,'Winner1'),_v(details,'WinnerX'),_v(details,'Winner2'))
    signals=sum(x is not None for x in [hx,ax,hp,ap,odds])
    if hx is None or ax is None:
        if hp is not None and ap is not None:
            hx=1.15+1.35*hp;ax=1.15+1.35*ap
        elif odds:
            hx=1.0+1.55*odds[0];ax=1.0+1.55*odds[2]
        else:hx=ax=1.15
    hs,as_=_score(hx,ax)
    if hs==as_ and hp is not None and ap is not None and abs(hp-ap)>.22:
        if hp>ap:hs=min(6,hs+1)
        else:as_=min(6,as_+1)
    outcome='home' if hs>as_ else ('away' if as_>hs else 'draw')
    probs=None
    if odds:probs=odds
    elif hp is not None and ap is not None:
        draw=max(.12,1-hp-ap);s=hp+draw+ap;probs=[hp/s,draw/s,ap/s]
    confidence=42
    if probs:confidence=round(max(probs)*100)
    confidence=max(35,min(82,confidence))
    quality='high' if signals>=4 else ('medium' if signals>=2 else 'low')
    factors=[f'Ожидаемые голы модели: {hx:.2f} — {ax:.2f}']
    if probs:factors.append(f'Вероятности 1/X/2: {probs[0]*100:.0f}% / {probs[1]*100:.0f}% / {probs[2]*100:.0f}%')
    if hp is not None and ap is not None:factors.append(f'Glicko: хозяева {hp*100:.0f}%, гости {ap*100:.0f}%')
    source='sstats-model' if signals else 'baseline'
    return {'match_id':match.id,'home_score':hs,'away_score':as_,'outcome':outcome,'confidence':confidence,'data_quality':quality,'source':source,'xg':{'home':round(hx,2),'away':round(ax,2)},'probabilities':{'home':round(probs[0]*100,1),'draw':round(probs[1]*100,1),'away':round(probs[2]*100,1)} if probs else None,'reasoning':'Оракул сводит xG, Glicko и рыночные коэффициенты. Чем меньше доступных сигналов, тем ниже качество прогноза.','key_factors':factors,'failure_risks':['Составы, травмы и ротация могут изменить баланс','Красная карточка или ранний гол резко меняют сценарий'],'details_errors':errors}
