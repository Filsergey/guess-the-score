import json, math
from fastapi import APIRouter, Depends, HTTPException
from openai import AsyncOpenAI
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import get_settings
from app.database import get_db
from app.models import Match, Team
from app.providers.sstats import SStatsProvider

router=APIRouter(prefix='/api/oracle',tags=['oracle']);settings=get_settings()
def _num(v):
    try:x=float(v);return x if math.isfinite(x) else None
    except (TypeError,ValueError):return None
def _prob(v):
    x=_num(v)
    if x is None:return None
    if x>1:x/=100
    return max(0.,min(1.,x))
def _first(p):
    d=p.get('data') or p.get('response') or [];return d[0] if isinstance(d,list) and d else (d if isinstance(d,dict) else {})
def _v(d,n):return d.get(n[:1].lower()+n[1:],d.get(n))
def _score(h,a):return min(6,max(0,int(math.floor(max(.15,min(4.5,h))+.35)))),min(6,max(0,int(math.floor(max(.15,min(4.5,a))+.35))))
def _odds_probs(h,d,a):
    vals=[_num(h),_num(d),_num(a)]
    if not all(x and x>1 for x in vals):return None
    inv=[1/x for x in vals];s=sum(inv);return [x/s for x in inv]
def _signals(d,g):return {'glicko_xg':{'home':_num(_v(d,'GlickoXgHome')) or _num(_v(g,'XgHome')),'away':_num(_v(d,'GlickoXgAway')) or _num(_v(g,'XgAway'))},'odds_xg':{'home':_num(_v(d,'OddsXgHome')),'away':_num(_v(d,'OddsXgAway'))},'glicko_win_probability':{'home':_prob(_v(d,'GlickoWinProbHome')) or _prob(_v(g,'WinProbHome')),'away':_prob(_v(d,'GlickoWinProbAway')) or _prob(_v(g,'WinProbAway'))},'odds':{'home':_num(_v(d,'Winner1')),'draw':_num(_v(d,'WinnerX')),'away':_num(_v(d,'Winner2'))}}
async def _load(m):
    d={};g={};errors=[]
    if m.provider=='sstats':
        p=SStatsProvider()
        try:d=_first(await p.query_game_details(m.provider_id))
        except Exception as e:errors.append(f'details:{type(e).__name__}')
        try:g=_first(await p.get_glicko(m.provider_id))
        except Exception as e:errors.append(f'glicko:{type(e).__name__}')
    return d,g,errors
async def _recent_form(team_id,before,db,limit=6):
    rows=(await db.execute(select(Match).where(Match.kickoff_at<before,Match.home_goals.is_not(None),Match.away_goals.is_not(None),or_(Match.home_team_id==team_id,Match.away_team_id==team_id)).order_by(Match.kickoff_at.desc()).limit(limit))).scalars().all()
    if not rows:return {'count':0,'gf':None,'ga':None,'ppg':None}
    gf=ga=pts=0
    for m in rows:
        a,b=(m.home_goals,m.away_goals) if m.home_team_id==team_id else (m.away_goals,m.home_goals);gf+=a;ga+=b;pts+=3 if a>b else (1 if a==b else 0)
    n=len(rows);return {'count':n,'gf':round(gf/n,2),'ga':round(ga/n,2),'ppg':round(pts/n,2)}
def _form_xg(h,a):
    if h['count']<2 or a['count']<2:return None,None
    return max(.2,min(3.8,(h['gf']+a['ga'])/2*1.08)),max(.2,min(3.8,(a['gf']+h['ga'])/2))
def _json_text(text):
    t=text.strip();t=t[t.find('{'):t.rfind('}')+1] if '{' in t and '}' in t else t;return json.loads(t)
async def _web_oracle(match,home,away,local_context):
    if not settings.openai_oracle_enabled or not settings.openai_api_key:return None
    client=AsyncOpenAI(api_key=settings.openai_api_key)
    prompt=f'''Ты футбольный аналитик приложения «Угадай счёт». Исследуй в интернете матч {home.name} — {away.name}, начало {match.kickoff_at.isoformat()}, сезон {match.season}. Используй свежие и надёжные источники. Найди: последние 5-10 матчей команд во всех турнирах, домашнюю/гостевую форму, последние очные встречи, голы/xG если доступны, травмы/дисквалификации, ожидаемые составы, турнирный контекст и актуальные предматчевые новости. Не выдумывай отсутствующие факты. Наши структурированные данные: {json.dumps(local_context,ensure_ascii=False,default=str)}. На основе совокупности данных дай прогноз точного счёта. Верни ТОЛЬКО JSON: {{"home_score":int,"away_score":int,"confidence":int 0-100,"data_quality":"high|medium|low","probabilities":{{"home":number,"draw":number,"away":number}},"reasoning":"краткое объяснение на русском","form":{{"home":"кратко","away":"кратко"}},"head_to_head":"кратко или нет данных","injuries":["..."],"key_factors":["..."],"failure_risks":["..."],"researched_at":"ISO datetime"}}. Вероятности должны суммироваться примерно в 100.'''
    try:
        r=await client.responses.create(model=settings.openai_oracle_model,tools=[{'type':'web_search'}],tool_choice='auto',include=['web_search_call.action.sources'],input=prompt)
        data=_json_text(r.output_text);sources=[]
        for item in r.output:
            if getattr(item,'type',None)=='web_search_call':
                action=getattr(item,'action',None)
                for src in (getattr(action,'sources',None) or []):
                    url=getattr(src,'url',None);title=getattr(src,'title',None)
                    if url and not any(x['url']==url for x in sources):sources.append({'title':title or url,'url':url})
        data['sources']=sources[:10];data['source']='openai-web';return data
    except Exception:return None

@router.get('/matches/{match_id}')
async def oracle_prediction(match_id:int,db:AsyncSession=Depends(get_db)):
    match=await db.get(Match,match_id)
    if match is None:raise HTTPException(404,'Match not found')
    home=await db.get(Team,match.home_team_id);away=await db.get(Team,match.away_team_id)
    d,g,errors=await _load(match);s=_signals(d,g);hf=await _recent_form(match.home_team_id,match.kickoff_at,db);af=await _recent_form(match.away_team_id,match.kickoff_at,db)
    local={'sstats':s,'database_form':{'home':hf,'away':af}}
    researched=await _web_oracle(match,home,away,local)
    if researched:
        researched.update({'match_id':match.id,'details_errors':errors});return researched
    fh,fa=_form_xg(hf,af);rh=s['glicko_xg']['home'] or s['odds_xg']['home'];ra=s['glicko_xg']['away'] or s['odds_xg']['away'];hp=s['glicko_win_probability']['home'];ap=s['glicko_win_probability']['away'];odds=_odds_probs(s['odds']['home'],s['odds']['draw'],s['odds']['away']);hx,ax=rh,ra;used_form=False
    if hx is None or ax is None:
        if fh is not None:hx,ax=fh,fa;used_form=True
        elif hp is not None and ap is not None:hx,ax=1.15+1.35*hp,1.15+1.35*ap
        elif odds:hx,ax=1+1.55*odds[0],1+1.55*odds[2]
        else:hx=ax=1.15
    hs,as_=_score(hx,ax);probs=odds
    if probs is None and fh is not None:
        diff=hx-ax;ph=max(.18,min(.62,.36+diff*.12));pa=max(.18,min(.62,.34-diff*.12));pd=max(.18,1-ph-pa);z=ph+pd+pa;probs=[ph/z,pd/z,pa/z]
    factors=[]
    if rh is not None and ra is not None:factors.append(f'xG модели: {rh:.2f} — {ra:.2f}')
    elif used_form:factors.append(f'Оценка по форме: {hx:.2f} — {ax:.2f}')
    return {'match_id':match.id,'home_score':hs,'away_score':as_,'outcome':'home' if hs>as_ else ('away' if as_>hs else 'draw'),'confidence':max(35,min(82,round(max(probs)*100) if probs else 42)),'data_quality':'medium' if fh is not None else 'low','source':'database-form' if used_form else 'baseline','xg':{'home':round(rh,2),'away':round(ra,2)} if rh is not None and ra is not None else None,'probabilities':{'home':round(probs[0]*100,1),'draw':round(probs[1]*100,1),'away':round(probs[2]*100,1)} if probs else None,'reasoning':'Веб-исследование ИИ недоступно; используется резервная модель по нашим данным.','key_factors':factors or ['Недостаточно данных'],'failure_risks':['Составы и травмы могут изменить баланс'],'details_errors':errors}
