import math
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
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
def _signals(details,glicko):
    return {
        'glicko_xg':{'home':_num(_v(details,'GlickoXgHome')) or _num(_v(glicko,'XgHome')),'away':_num(_v(details,'GlickoXgAway')) or _num(_v(glicko,'XgAway'))},
        'odds_xg':{'home':_num(_v(details,'OddsXgHome')),'away':_num(_v(details,'OddsXgAway'))},
        'glicko_win_probability':{'home':_prob(_v(details,'GlickoWinProbHome')) or _prob(_v(glicko,'WinProbHome')),'away':_prob(_v(details,'GlickoWinProbAway')) or _prob(_v(glicko,'WinProbAway'))},
        'odds':{'home':_num(_v(details,'Winner1')),'draw':_num(_v(details,'WinnerX')),'away':_num(_v(details,'Winner2'))},
        'ratings':{'home':_num(_v(details,'GlickoRatingHome')) or _num(_v(glicko,'RatingHome')),'away':_num(_v(details,'GlickoRatingAway')) or _num(_v(glicko,'RatingAway'))},
    }
async def _load(match):
    details={};glicko={};errors=[]
    if match.provider=='sstats':
        p=SStatsProvider()
        try:details=_first(await p.query_game_details(match.provider_id))
        except Exception as e:errors.append(f'details:{type(e).__name__}')
        try:glicko=_first(await p.get_glicko(match.provider_id))
        except Exception as e:errors.append(f'glicko:{type(e).__name__}')
    return details,glicko,errors
async def _recent_form(team_id:int,before,db:AsyncSession,limit:int=6):
    stmt=(select(Match).where(Match.kickoff_at<before,Match.home_goals.is_not(None),Match.away_goals.is_not(None),or_(Match.home_team_id==team_id,Match.away_team_id==team_id)).order_by(Match.kickoff_at.desc()).limit(limit))
    rows=(await db.execute(stmt)).scalars().all()
    if not rows:return {'count':0,'gf':None,'ga':None,'ppg':None,'matches':[]}
    gf=ga=pts=0;items=[]
    for m in rows:
        if m.home_team_id==team_id:a,b=m.home_goals,m.away_goals
        else:a,b=m.away_goals,m.home_goals
        gf+=a;ga+=b;pts+=3 if a>b else (1 if a==b else 0);items.append({'match_id':m.id,'gf':a,'ga':b,'kickoff_at':m.kickoff_at})
    n=len(rows);return {'count':n,'gf':round(gf/n,2),'ga':round(ga/n,2),'ppg':round(pts/n,2),'matches':items}

def _form_xg(home_form,away_form):
    if home_form['count']<2 or away_form['count']<2:return None,None
    hx=(home_form['gf']+away_form['ga'])/2
    ax=(away_form['gf']+home_form['ga'])/2
    hx*=1.08
    return max(.2,min(3.8,hx)),max(.2,min(3.8,ax))

@router.get('/matches/{match_id}/diagnostics')
async def oracle_diagnostics(match_id:int,db:AsyncSession=Depends(get_db)):
    match=await db.get(Match,match_id)
    if match is None:raise HTTPException(404,'Match not found')
    details,glicko,errors=await _load(match);signals=_signals(details,glicko)
    hf=await _recent_form(match.home_team_id,match.kickoff_at,db);af=await _recent_form(match.away_team_id,match.kickoff_at,db)
    return {'match_id':match.id,'provider':match.provider,'provider_id':match.provider_id,'errors':errors,'sources':{'games_query':{'available':bool(details),'fields':sorted(details.keys())},'glicko':{'available':bool(glicko),'fields':sorted(glicko.keys())},'database_form':{'available':hf['count']>=2 and af['count']>=2,'home':hf,'away':af}},'signals':signals}

@router.get('/matches/{match_id}')
async def oracle_prediction(match_id:int,db:AsyncSession=Depends(get_db)):
    match=await db.get(Match,match_id)
    if match is None:raise HTTPException(404,'Match not found')
    details,glicko,errors=await _load(match);s=_signals(details,glicko)
    hf=await _recent_form(match.home_team_id,match.kickoff_at,db);af=await _recent_form(match.away_team_id,match.kickoff_at,db);form_hx,form_ax=_form_xg(hf,af)
    real_hx=s['glicko_xg']['home'] or s['odds_xg']['home'];real_ax=s['glicko_xg']['away'] or s['odds_xg']['away']
    hp=s['glicko_win_probability']['home'];ap=s['glicko_win_probability']['away'];odds=_odds_probs(s['odds']['home'],s['odds']['draw'],s['odds']['away'])
    provider_signals=sum(x is not None for x in [real_hx,real_ax,hp,ap,odds]);form_available=form_hx is not None and form_ax is not None
    hx,ax=real_hx,real_ax;used_form=False
    if hx is None or ax is None:
        if form_available:hx,ax=form_hx,form_ax;used_form=True
        elif hp is not None and ap is not None:hx=1.15+1.35*hp;ax=1.15+1.35*ap
        elif odds:hx=1.0+1.55*odds[0];ax=1.0+1.55*odds[2]
        else:hx=ax=1.15
    hs,as_=_score(hx,ax)
    if hs==as_ and hp is not None and ap is not None and abs(hp-ap)>.22:
        if hp>ap:hs=min(6,hs+1)
        else:as_=min(6,as_+1)
    outcome='home' if hs>as_ else ('away' if as_>hs else 'draw');probs=odds
    if probs is None and hp is not None and ap is not None:
        draw=max(.12,1-hp-ap);total=hp+draw+ap;probs=[hp/total,draw/total,ap/total]
    if probs is None and form_available:
        diff=hx-ax;home=max(.18,min(.62,.36+diff*.12));away=max(.18,min(.62,.34-diff*.12));draw=max(.18,1-home-away);total=home+draw+away;probs=[home/total,draw/total,away/total]
    confidence=max(35,min(82,round(max(probs)*100) if probs else 42))
    if provider_signals>=4:quality='high'
    elif provider_signals>=2 or (form_available and min(hf['count'],af['count'])>=4):quality='medium'
    else:quality='low'
    factors=[]
    if real_hx is not None and real_ax is not None:factors.append(f'Ожидаемые голы модели: {real_hx:.2f} — {real_ax:.2f}')
    elif used_form:factors.append(f'Форма последних матчей: ожидаемые голы {hx:.2f} — {ax:.2f}')
    if probs:factors.append(f'Вероятности 1/X/2: {probs[0]*100:.0f}% / {probs[1]*100:.0f}% / {probs[2]*100:.0f}%')
    if hp is not None and ap is not None:factors.append(f'Glicko: хозяева {hp*100:.0f}%, гости {ap*100:.0f}%')
    if form_available:factors.append(f'Последние матчи: хозяева {hf["gf"]} забито / {hf["ga"]} пропущено; гости {af["gf"]} / {af["ga"]}')
    if not factors:factors.append('Предматчевые показатели пока недоступны')
    source='sstats-model' if provider_signals else ('database-form' if used_form else 'baseline')
    reasoning='Оракул использует SStats (xG, Glicko, коэффициенты) и, когда этих данных нет, реальную форму команд по завершённым матчам в нашей базе.'
    return {'match_id':match.id,'home_score':hs,'away_score':as_,'outcome':outcome,'confidence':confidence,'data_quality':quality,'source':source,'xg':{'home':round(real_hx,2),'away':round(real_ax,2)} if real_hx is not None and real_ax is not None else None,'form_estimate':{'home':round(form_hx,2),'away':round(form_ax,2)} if form_available else None,'form':{'home':hf,'away':af},'probabilities':{'home':round(probs[0]*100,1),'draw':round(probs[1]*100,1),'away':round(probs[2]*100,1)} if probs else None,'reasoning':reasoning,'key_factors':factors,'failure_risks':['Составы, травмы и ротация могут изменить баланс','Красная карточка или ранний гол резко меняют сценарий'],'details_errors':errors}
