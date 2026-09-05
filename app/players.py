import asyncio
import re
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import get_settings
from app.database import get_db
from app.models import Player, User
from app.providers.uefa import UEFAProvider, UEFATeam

router = APIRouter(tags=['players'])
settings = get_settings()
POPULAR_TOKENS = ('мбаппе','кейн','холанд','ямаль','винисиус','дембеле','сака','рафинья','альварес','беллингем','педри','вирц','мусиала','лаутаро')
CATALOG_REFRESH_DAYS = 7
POSITION_RU = {'Goalkeeper':'Вратарь','Defender':'Защитник','Midfielder':'Полузащитник','Attacker':'Нападающий','Forward':'Нападающий'}

def _position_ru(value): return POSITION_RU.get(value or '',value)
def _is_popular(name):
 low=(name or '').casefold();return any(token in low for token in POPULAR_TOKENS)
def _has_cyrillic(value): return bool(value and re.search(r'[А-Яа-яЁё]',value))
def current_uefa_season_year(now=None):
 now=now or datetime.now(timezone.utc);return now.year+1 if now.month>=7 else now.year

async def _download_photo(client,url):
 if not url or not url.startswith('https://'):return None,None
 try:
  r=await client.get(url,headers={'User-Agent':'guess-the-score/1.0'});ctype=(r.headers.get('content-type') or '').split(';')[0].lower()
  if r.status_code==200 and r.content and ctype.startswith('image/') and len(r.content)<=2*1024*1024:return r.content,ctype
 except Exception:pass
 return None,None

async def sync_uefa_team_players(db:AsyncSession,team:UEFATeam,season_year:int,download_photos:bool=True)->dict:
 rows,diagnostic=await UEFAProvider().squad(team.id);ids=[row.id for row in rows]
 old=(await db.execute(select(Player).where(Player.provider=='uefa',Player.provider_id.in_(ids)))).scalars().all() if ids else [];existing={p.provider_id:p for p in old}
 if rows and download_photos:
  async with httpx.AsyncClient(timeout=10,follow_redirects=True,limits=httpx.Limits(max_connections=8)) as client:
   sem=asyncio.Semaphore(6)
   async def dl(row):
    async with sem:return await _download_photo(client,row.photo_url)
   photos_result=await asyncio.gather(*(dl(row) for row in rows))
 else:photos_result=[(None,None) for _ in rows]
 now=datetime.now(timezone.utc);saved=photos=photo_urls=0
 for i,row in enumerate(rows):
  p=existing.get(row.id)
  if not p:p=Player(provider='uefa',provider_id=row.id,name=row.name);db.add(p)
  p.name=row.name;p.display_name=row.name;p.team_provider_id=team.id;p.team_name=team.name_ru or team.name;p.position=_position_ru(row.position);p.shirt_number=row.number;p.nationality=row.nationality;p.photo_source_url=row.photo_url;p.has_photo=bool(row.photo_url or p.photo_data);p.is_active=True;p.is_popular=_is_popular(row.name);p.season=season_year;p.updated_at=now
  if row.photo_url:photo_urls+=1
  data,ctype=photos_result[i]
  if data:p.photo_data=data;p.photo_media_type=ctype;p.has_photo=True;photos+=1
  saved+=1
 if ids:
  stale=(await db.execute(select(Player).where(Player.provider=='uefa',Player.team_provider_id==team.id,Player.season==season_year,Player.is_active.is_(True),Player.provider_id.not_in(set(ids))))).scalars().all()
  for p in stale:p.is_active=False;p.updated_at=now
 await db.commit();return {'provider':'uefa','team':team.name,'team_ru':team.name_ru,'team_id':team.id,'received':len(rows),'saved':saved,'photo_urls':photo_urls,'photos_downloaded':photos,'diagnostic':diagnostic}

async def _player_rows(db,q,popular,limit):
 cols=(Player.id,Player.provider,Player.provider_id,Player.name,Player.display_name,Player.team_name,Player.position,Player.shirt_number,Player.nationality,Player.is_popular,Player.photo_source_url,(Player.photo_data.is_not(None)).label('has_photo_blob'))
 base=select(*cols).where(Player.is_active.is_(True),Player.provider=='uefa')
 if q:
  like=f"%{q.strip()}%";base=base.where(or_(Player.name.ilike(like),Player.display_name.ilike(like),Player.team_name.ilike(like)))
 if popular:
  rows=(await db.execute(base.where(Player.is_popular.is_(True)).order_by(Player.name).limit(limit))).all()
  if rows:return rows
 return (await db.execute(base.order_by(Player.is_popular.desc(),Player.name).limit(limit))).all()

@router.get('/api/players')
async def list_players(q:str|None=Query(default=None,max_length=100),popular:bool=False,limit:int=Query(default=30,ge=1,le=100),user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
 del user;rows=await _player_rows(db,q,popular,limit);return {'count':len(rows),'response':[{'id':r.id,'provider':r.provider,'provider_id':r.provider_id,'name':r.name,'display_name':r.display_name or r.name,'team':r.team_name,'team_original':r.team_name,'position':r.position,'number':r.shirt_number,'nationality':r.nationality,'photo':f'/api/players/{r.id}/photo' if (r.has_photo_blob or r.photo_source_url) else None,'has_photo':bool(r.has_photo_blob or r.photo_source_url),'popular':r.is_popular} for r in rows]}

@router.get('/api/players/catalog-status',include_in_schema=False)
async def player_catalog_status(db:AsyncSession=Depends(get_db)):
 total=(await db.execute(select(func.count(Player.id).where(Player.provider=='uefa')))).scalar_one();active=(await db.execute(select(func.count(Player.id)).where(Player.provider=='uefa',Player.is_active.is_(True)))).scalar_one();with_blob=(await db.execute(select(func.count(Player.id)).where(Player.provider=='uefa',Player.photo_data.is_not(None)))).scalar_one();with_source=(await db.execute(select(func.count(Player.id)).where(Player.provider=='uefa',Player.photo_source_url.is_not(None)))).scalar_one();popular=(await db.execute(select(func.count(Player.id)).where(Player.provider=='uefa',Player.is_popular.is_(True)))).scalar_one();return {'total':total,'active':active,'uefa':total,'with_photo_blob':with_blob,'with_photo_source':with_source,'popular':popular}

@router.get('/api/players/uefa-check',include_in_schema=False)
async def uefa_check(team_id:int=Query(default=50080,ge=1)):
 try:rows,d=await UEFAProvider().squad(team_id)
 except Exception as e:return {'ok':False,'team_id':team_id,'error':type(e).__name__,'message':str(e)[:300]}
 return {'ok':bool(rows),'team_id':team_id,**d,'players':len(rows),'with_photo':sum(bool(x.photo_url) for x in rows),'sample':[{'id':x.id,'name':x.name,'number':x.number,'nationality':x.nationality,'position':x.position,'photo':x.photo_url,'profile':x.profile_url} for x in rows[:8]]}

async def _refresh_player(db,p):
 if p.provider!='uefa' or not p.team_provider_id:return
 if p.photo_source_url and p.team_name and p.position and p.nationality and _has_cyrillic(p.name):return
 try:
  season=p.season or current_uefa_season_year();teams=await UEFAProvider().competition_teams(1,season);team=next((x for x in teams if x.id==p.team_provider_id),None)
  if team:await sync_uefa_team_players(db,team,season,False);await db.refresh(p)
 except Exception:await db.rollback()

@router.get('/api/players/{player_id}/photo',include_in_schema=False)
async def player_photo(player_id:int,db:AsyncSession=Depends(get_db)):
 p=await db.get(Player,player_id)
 if not p or p.provider!='uefa':raise HTTPException(404,'Player not found')
 if p.photo_data:return Response(content=p.photo_data,media_type=p.photo_media_type or 'image/jpeg',headers={'Cache-Control':'public, max-age=604800, immutable'})
 await _refresh_player(db,p)
 if p.photo_source_url:
  async with httpx.AsyncClient(timeout=8,follow_redirects=True) as client:data,ctype=await _download_photo(client,p.photo_source_url)
  if data:p.photo_data=data;p.photo_media_type=ctype;p.has_photo=True;await db.commit();return Response(content=data,media_type=ctype or 'image/jpeg',headers={'Cache-Control':'public, max-age=604800, immutable'})
 raise HTTPException(404,'Player photo not found')

@router.post('/api/admin/players/sync')
async def sync_catalog(limit_teams:int=Query(default=5,ge=1,le=36),offset:int=Query(default=0,ge=0),download_photos:bool=True,competition_id:int=1,season_year:int=Query(default=2027,ge=2000,le=2100),x_admin_token:str|None=Header(default=None),db:AsyncSession=Depends(get_db)):
 if not settings.admin_sync_token:raise HTTPException(503,'ADMIN_SYNC_TOKEN is not configured')
 if x_admin_token!=settings.admin_sync_token:raise HTTPException(401,'Invalid admin token')
 all_teams=await UEFAProvider().competition_teams(competition_id,season_year);teams=all_teams[offset:offset+limit_teams];results=[]
 for team in teams:
  try:results.append(await sync_uefa_team_players(db,team,season_year,download_photos))
  except Exception as e:await db.rollback();results.append({'team':team.name,'error':type(e).__name__,'message':str(e)[:180]})
 total=(await db.execute(select(func.count(Player.id)).where(Player.provider=='uefa'))).scalar_one();return {'provider':'uefa','season_year':season_year,'teams_available':len(all_teams),'teams_processed':len(results),'total_players':total,'results':results}

async def _team_catalog_needs_refresh(db,team_id,season):
 rows=(await db.execute(select(Player.name,Player.updated_at,Player.team_name,Player.position,Player.nationality,Player.photo_source_url).where(Player.provider=='uefa',Player.team_provider_id==team_id,Player.season==season,Player.is_active.is_(True)))).all()
 if len(rows)<10 or not any(_has_cyrillic(r.name) for r in rows) or any(not r.team_name or not r.position or not r.nationality or not r.photo_source_url for r in rows):return True
 last=max((r.updated_at for r in rows if r.updated_at),default=None)
 if not last:return True
 if last.tzinfo is None:last=last.replace(tzinfo=timezone.utc)
 return last<datetime.now(timezone.utc)-timedelta(days=CATALOG_REFRESH_DAYS)

async def bootstrap_popular_players():
 from app.database import SessionLocal
 season=current_uefa_season_year()
 try:teams=await UEFAProvider().competition_teams(1,season)
 except Exception:return
 try:
  async with SessionLocal() as db:
   for team in teams:
    try:
     if await _team_catalog_needs_refresh(db,team.id,season):await sync_uefa_team_players(db,team,season,False);await asyncio.sleep(.15)
    except Exception:await db.rollback()
 except Exception:return
