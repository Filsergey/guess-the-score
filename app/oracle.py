import json, math, re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from openai import AsyncOpenAI
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import Match, OraclePrediction, Team
from app.providers.sstats import SStatsProvider

router=APIRouter(prefix='/api/oracle',tags=['oracle']);settings=get_settings()
CACHE_SCHEMA_VERSION=2

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

def _clean_text(v):
    if v is None:return None
    s=str(v)
    s=re.sub(r'\(\[[^\]]+\]\s*\(https?://[^\s)]+(?:\([^)]*\)[^\s)]*)?\)\)', '', s)
    s=re.sub(r'\[[^\]]+\]\s*\(https?://[^)]+\)', '', s)
    s=re.sub(r'https?://\S+', '', s);s=re.sub(r'\(\s*\)', '', s);s=re.sub(r'\s+([,.;:!?])', r'\1', s)
    return re.sub(r'\s{2,}', ' ', s).strip()

def _match_rows(v,kind='recent'):
    if not isinstance(v,list):return []
    rows=[]
    for x in v[:5]:
        if not isinstance(x,dict):continue
        if kind=='h2h':
            row={'date':_clean_text(x.get('date')),'home':_clean_text(x.get('home')),'away':_clean_text(x.get('away')),'score':_clean_text(x.get('score')),'competition':_clean_text(x.get('competition'))}
            if row['home'] and row['away'] and row['score']:rows.append(row)
        else:
            row={'date':_clean_text(x.get('date')),'opponent':_clean_text(x.get('opponent')),'score':_clean_text(x.get('score')),'competition':_clean_text(x.get('competition')),'result':str(x.get('result') or '').upper()[:1]}
            if row['opponent'] and row['score']:rows.append(row)
    return rows

def _normalize_web(data):
    hs=max(0,min(20,int(_num(data.get('home_score')) or 0)));as_=max(0,min(20,int(_num(data.get('away_score')) or 0)))
    p=data.get('probabilities') if isinstance(data.get('probabilities'),dict) else {};ph=_num(p.get('home'));pd=_num(p.get('draw'));pa=_num(p.get('away'))
    if all(x is not None and x>=0 for x in (ph,pd,pa)):
        total=ph+pd+pa
        if total>0:ph,pd,pa=[round(x*100/total,1) for x in (ph,pd,pa)]
        else:ph=pd=pa=None
    else:ph=pd=pa=None
    confidence=max(0,min(100,int(_num(data.get('confidence')) or max([x for x in (ph,pd,pa) if x is not None],default=50))))
    q=str(data.get('data_quality') or 'medium').lower();q=q if q in ('high','medium','low') else 'medium'
    def strings(v):return [_clean_text(x) for x in v if _clean_text(x)] if isinstance(v,list) else []
    form=data.get('form') if isinstance(data.get('form'),dict) else None
    if form:form={'home':_clean_text(form.get('home')),'away':_clean_text(form.get('away'))}
    recent=data.get('recent_matches') if isinstance(data.get('recent_matches'),dict) else {}
    return {'schema_version':CACHE_SCHEMA_VERSION,'home_score':hs,'away_score':as_,'outcome':'home' if hs>as_ else ('away' if as_>hs else 'draw'),'confidence':confidence,'data_quality':q,'probabilities':{'home':ph,'draw':pd,'away':pa} if ph is not None else None,'reasoning':_clean_text(data.get('reasoning')) or 'ИИ выполнил веб-исследование матча.','form':form,'recent_matches':{'home':_match_rows(recent.get('home')),'away':_match_rows(recent.get('away'))},'head_to_head':_clean_text(data.get('head_to_head')),'head_to_head_matches':_match_rows(data.get('head_to_head_matches'),'h2h'),'injuries':strings(data.get('injuries')),'key_factors':strings(data.get('key_factors')),'failure_risks':strings(data.get('failure_risks')),'researched_at':data.get('researched_at')}

async def _match_context(match,db):
    home=await db.get(Team,match.home_team_id);away=await db.get(Team,match.away_team_id)
    d,g,errors=await _load(match);s=_signals(d,g);hf=await _recent_form(match.home_team_id,match.kickoff_at,db);af=await _recent_form(match.away_team_id,match.kickoff_at,db)
    return {'match':match,'home':home,'away':away,'local':{'sstats':s,'database_form':{'home':hf,'away':af}},'errors':errors,'signals':s,'home_form':hf,'away_form':af}

async def _web_oracle_batch(items):
    if not settings.openai_oracle_enabled or not settings.openai_api_key:return {}
    client=AsyncOpenAI(api_key=settings.openai_api_key)
    compact=[{'match_id':x['match'].id,'home':x['home'].name,'away':x['away'].name,'kickoff_at':x['match'].kickoff_at.isoformat(),'season':x['match'].season,'local':x['local']} for x in items]
    prompt=f'''Ты футбольный аналитик приложения «Угадай счёт». Исследуй СРАЗУ несколько футбольных матчей одним веб-исследованием. Матчи: {json.dumps(compact,ensure_ascii=False,default=str)}.
Для КАЖДОГО match_id отдельно проверь свежие данные. ОБЯЗАТЕЛЬНО найди и верни: (1) ровно последние 5 завершённых матчей команды хозяев до указанной даты матча, с датой, соперником, счётом с точки зрения этой команды, турниром и W/D/L; (2) ровно последние 5 завершённых матчей команды гостей в том же формате; (3) до 5 последних очных встреч этих двух клубов до даты прогнозируемого матча — дата, кто был хозяином/гостем, итоговый счёт и турнир. Самую свежую очную встречу поставь первой. Если очных встреч не было, верни пустой массив и явно скажи это в head_to_head.
Также проверь домашнюю/гостевую форму, голы и xG/xGA если надёжно доступны, подтверждённые травмы и дисквалификации, ожидаемые составы/ротацию, турнирный контекст, свежие новости и рыночные коэффициенты. Сверяй точные команды и дату матча. Не смешивай факты разных матчей. Не включай матчи, сыгранные ПОСЛЕ kickoff_at прогнозируемой встречи. Не выдумывай отсутствующие данные. Приоритет источников: официальные сайты клубов и турниров, UEFA, крупные спортивные СМИ и надёжные статистические сайты.
Не вставляй URL, markdown-ссылки, названия источников или citations внутрь текстовых полей. Верни ТОЛЬКО JSON без markdown вида {{"matches":[{{"match_id":123,"home_score":1,"away_score":1,"confidence":60,"data_quality":"high|medium|low","probabilities":{{"home":30,"draw":35,"away":35}},"reasoning":"2-4 конкретных предложения по-русски","form":{{"home":"кратко","away":"кратко"}},"recent_matches":{{"home":[{{"date":"YYYY-MM-DD","opponent":"Team","score":"2:1","competition":"Competition","result":"W"}}],"away":[{{"date":"YYYY-MM-DD","opponent":"Team","score":"0:1","competition":"Competition","result":"L"}}]}},"head_to_head":"краткий итог истории противостояний и когда встречались в последний раз","head_to_head_matches":[{{"date":"YYYY-MM-DD","home":"Team A","away":"Team B","score":"2:1","competition":"Competition"}}],"injuries":["..."],"key_factors":["3-6 факторов"],"failure_risks":["2-4 риска"],"researched_at":"ISO datetime"}}]}}. Вероятности каждого матча должны суммироваться до 100.'''
    try:
        r=await client.responses.create(model=settings.openai_oracle_model,tools=[{'type':'web_search'}],tool_choice='auto',input=prompt)
        raw=_json_text(r.output_text);rows=raw.get('matches') if isinstance(raw,dict) else None
        if not isinstance(rows,list):return {}
        result={};valid={x['match'].id for x in items}
        for row in rows:
            if not isinstance(row,dict):continue
            mid=int(_num(row.get('match_id')) or 0)
            if mid not in valid:continue
            data=_normalize_web(row);data.update({'match_id':mid,'source':'openai-web'});result[mid]=data
        return result
    except Exception:return {}

async def _save_cache(db,match_id,data):
    row=(await db.execute(select(OraclePrediction).where(OraclePrediction.match_id==match_id))).scalar_one_or_none();now=datetime.now(timezone.utc)
    data['schema_version']=CACHE_SCHEMA_VERSION;payload=json.dumps(data,ensure_ascii=False,default=str)
    if row is None:row=OraclePrediction(match_id=match_id,payload_json=payload,source=data.get('source','openai-web'),generated_at=now,updated_at=now);db.add(row)
    else:row.payload_json=payload;row.source=data.get('source','openai-web');row.generated_at=now;row.updated_at=now

async def _get_cache(db,match_id):
    row=(await db.execute(select(OraclePrediction).where(OraclePrediction.match_id==match_id))).scalar_one_or_none()
    if not row:return None
    try:
        data=json.loads(row.payload_json)
        if int(data.get('schema_version') or 0)<CACHE_SCHEMA_VERSION:return None
        data.pop('sources',None);data['cached']=True;data['generated_at']=row.generated_at;return data
    except Exception:return None

def _needs_refresh(match,cache_row,now):
    if cache_row is None:return True
    try:
        cached=json.loads(cache_row.payload_json)
        if int(cached.get('schema_version') or 0)<CACHE_SCHEMA_VERSION:return True
    except Exception:return True
    if match.kickoff_at<=now:return False
    until=match.kickoff_at-now;age=now-cache_row.generated_at
    if until<=timedelta(hours=3):return age>timedelta(hours=2)
    if until<=timedelta(hours=30):return age>timedelta(hours=12)
    return False

async def _fallback(ctx):
    match=ctx['match'];s=ctx['signals'];hf=ctx['home_form'];af=ctx['away_form'];errors=ctx['errors']
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
    return {'schema_version':CACHE_SCHEMA_VERSION,'match_id':match.id,'home_score':hs,'away_score':as_,'outcome':'home' if hs>as_ else ('away' if as_>hs else 'draw'),'confidence':max(35,min(82,round(max(probs)*100) if probs else 42)),'data_quality':'medium' if fh is not None else 'low','source':'database-form' if used_form else 'baseline','xg':{'home':round(rh,2),'away':round(ra,2)} if rh is not None and ra is not None else None,'probabilities':{'home':round(probs[0]*100,1),'draw':round(probs[1]*100,1),'away':round(probs[2]*100,1)} if probs else None,'reasoning':'Веб-исследование ИИ недоступно; используется резервная модель по нашим данным.','recent_matches':{'home':[],'away':[]},'head_to_head':None,'head_to_head_matches':[],'key_factors':factors or ['Недостаточно данных'],'failure_risks':['Составы и травмы могут изменить баланс'],'details_errors':errors}

@router.post('/admin/generate-batch')
async def generate_batch(batch_size:int=Query(default=5,ge=1,le=10),hours_ahead:int=Query(default=120,ge=3,le=336),season:int|None=Query(default=None,ge=2020,le=2100),force:bool=Query(default=False),x_admin_token:str|None=Header(default=None),db:AsyncSession=Depends(get_db)):
    if not settings.admin_sync_token:raise HTTPException(503,'ADMIN_SYNC_TOKEN is not configured')
    if x_admin_token!=settings.admin_sync_token:raise HTTPException(401,'Invalid admin token')
    now=datetime.now(timezone.utc);end=now+timedelta(hours=hours_ahead)
    q=select(Match).where(Match.kickoff_at>now,Match.kickoff_at<=end).order_by(Match.kickoff_at)
    if season is not None:q=q.where(Match.season==season)
    matches=(await db.execute(q)).scalars().all();selected=[]
    for m in matches:
        cache=(await db.execute(select(OraclePrediction).where(OraclePrediction.match_id==m.id))).scalar_one_or_none()
        if force or _needs_refresh(m,cache,now):selected.append(m)
        if len(selected)>=batch_size:break
    if not selected:return {'requested':0,'generated':0,'message':'No Oracle predictions need refresh'}
    items=[await _match_context(m,db) for m in selected];generated=await _web_oracle_batch(items)
    for ctx in items:
        data=generated.get(ctx['match'].id)
        if data:
            data['details_errors']=ctx['errors'];await _save_cache(db,ctx['match'].id,data)
    await db.commit()
    return {'requested':len(selected),'generated':len(generated),'match_ids':[m.id for m in selected],'generated_ids':sorted(generated.keys()),'batch_size':batch_size,'hours_ahead':hours_ahead}

@router.get('/matches/{match_id}')
async def oracle_prediction(match_id:int,db:AsyncSession=Depends(get_db)):
    match=await db.get(Match,match_id)
    if match is None:raise HTTPException(404,'Match not found')
    cached=await _get_cache(db,match_id)
    if cached:return cached
    ctx=await _match_context(match,db);generated=await _web_oracle_batch([ctx]);data=generated.get(match_id)
    if data:
        data['details_errors']=ctx['errors'];await _save_cache(db,match_id,data);await db.commit();data['cached']=False;return data
    return await _fallback(ctx)