import asyncio
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import get_settings
from app.database import get_db
from app.localization import API_FOOTBALL_TEAM_IDS, team_name_ru
from app.models import Player, User
from app.providers.api_football import APIFootballProvider

router = APIRouter(tags=['players'])
settings = get_settings()

POPULAR_NAMES = {
    'Kylian Mbappe','Harry Kane','Erling Haaland','Lamine Yamal','Vinicius Junior','Ousmane Dembele',
    'Bukayo Saka','Raphinha','Julian Alvarez','Jude Bellingham','Pedri','Florian Wirtz','Jamal Musiala','Lautaro Martinez'
}

POSITION_RU = {
    'Goalkeeper':'Вратарь','Defender':'Защитник','Midfielder':'Полузащитник','Attacker':'Нападающий',
    'Forward':'Нападающий','Right Winger':'Нападающий','Left Winger':'Нападающий','Centre-Forward':'Нападающий',
    'Central Midfield':'Полузащитник','Attacking Midfield':'Полузащитник','Defensive Midfield':'Полузащитник',
    'Right-Back':'Защитник','Left-Back':'Защитник','Centre-Back':'Защитник'
}

def _position_ru(value: str | None) -> str | None:
    return POSITION_RU.get(value or '', value)

def _catalog_team_ids() -> list[tuple[str,int]]:
    seen=set();out=[]
    for name,team_id in API_FOOTBALL_TEAM_IDS.items():
        if team_id in seen:continue
        seen.add(team_id);out.append((name,team_id))
    return out

async def _download_photo(client:httpx.AsyncClient,url:str|None)->tuple[bytes|None,str|None]:
    if not url or not url.startswith('https://'):return None,None
    try:
        r=await client.get(url,headers={'User-Agent':'guess-the-score/1.0'});ctype=(r.headers.get('content-type') or '').split(';')[0].lower()
        if r.status_code==200 and r.content and ctype.startswith('image/') and len(r.content)<=2*1024*1024:return r.content,ctype
    except Exception:pass
    return None,None

async def sync_team_players(db:AsyncSession,team_name:str,team_id:int,download_photos:bool=True)->dict:
    payload=await APIFootballProvider().get_squad(team_id);response=payload.get('response') or []
    if not response:return {'team':team_name,'team_id':team_id,'received':0,'saved':0,'photos':0}
    root=response[0] if isinstance(response[0],dict) else {};api_team=root.get('team') if isinstance(root.get('team'),dict) else {};actual_team_name=api_team.get('name') or team_name
    rows=root.get('players') or [];rows=rows if isinstance(rows,list) else [];valid=[r for r in rows if isinstance(r,dict) and r.get('id') and r.get('name')]
    ids=[int(r['id']) for r in valid];existing_rows=(await db.execute(select(Player).where(Player.provider=='api-football',Player.provider_id.in_(ids)))).scalars().all() if ids else [];existing={p.provider_id:p for p in existing_rows}
    async with httpx.AsyncClient(timeout=8.0,follow_redirects=True,limits=httpx.Limits(max_connections=8)) as client:
        sem=asyncio.Semaphore(6)
        async def dl(row):
            async with sem:return await _download_photo(client,row.get('photo')) if download_photos else (None,None)
        photo_results=await asyncio.gather(*(dl(r) for r in valid)) if valid else []
    now=datetime.now(timezone.utc);saved=photos=0
    for idx,row in enumerate(valid):
        pid=int(row['id']);p=existing.get(pid)
        if not p:p=Player(provider='api-football',provider_id=pid,name=str(row['name']));db.add(p)
        p.name=str(row['name']);p.display_name=str(row['name']);p.team_provider_id=team_id;p.team_name=actual_team_name;p.position=_position_ru(row.get('position'));p.photo_source_url=row.get('photo');p.is_active=True;p.is_popular=p.name in POPULAR_NAMES;p.season=2026;p.updated_at=now
        if idx<len(photo_results):
            data,ctype=photo_results[idx]
            if data:p.photo_data=data;p.photo_media_type=ctype;photos+=1
        saved+=1
    await db.commit();return {'team':actual_team_name,'team_id':team_id,'received':len(valid),'saved':saved,'photos':photos}

@router.get('/api/players')
async def list_players(q:str|None=Query(default=None,max_length=100),popular:bool=Query(default=False),limit:int=Query(default=30,ge=1,le=100),user:User=Depends(get_current_user),db:AsyncSession=Depends(get_db)):
    del user
    stmt=select(Player.id,Player.provider_id,Player.name,Player.display_name,Player.team_name,Player.position,Player.is_popular,(Player.photo_data.is_not(None)).label('has_photo')).where(Player.is_active.is_(True))
    if q:
        like=f"%{q.strip()}%";stmt=stmt.where(or_(Player.name.ilike(like),Player.display_name.ilike(like),Player.team_name.ilike(like)))
    if popular:stmt=stmt.where(Player.is_popular.is_(True)).order_by(Player.name)
    else:stmt=stmt.order_by(Player.is_popular.desc(),Player.name)
    rows=(await db.execute(stmt.limit(limit))).all()
    return {'count':len(rows),'response':[{'id':r.id,'provider_id':r.provider_id,'name':r.name,'display_name':r.display_name or r.name,'team':team_name_ru(r.team_name) if r.team_name else None,'team_original':r.team_name,'position':r.position,'photo':f'/api/players/{r.id}/photo' if r.has_photo else None,'has_photo':bool(r.has_photo),'popular':r.is_popular} for r in rows]}

@router.get('/api/players/{player_id}/photo',include_in_schema=False)
async def player_photo_from_db(player_id:int,db:AsyncSession=Depends(get_db)):
    row=(await db.execute(select(Player.photo_data,Player.photo_media_type).where(Player.id==player_id))).first()
    if not row or not row.photo_data:raise HTTPException(404,'Player photo not found in database')
    return Response(content=row.photo_data,media_type=row.photo_media_type or 'image/jpeg',headers={'Cache-Control':'public, max-age=604800, immutable'})

@router.post('/api/admin/players/sync')
async def sync_players_catalog(limit_teams:int=Query(default=5,ge=1,le=50),offset:int=Query(default=0,ge=0),download_photos:bool=Query(default=True),x_admin_token:str|None=Header(default=None),db:AsyncSession=Depends(get_db)):
    if not settings.admin_sync_token:raise HTTPException(503,'ADMIN_SYNC_TOKEN is not configured')
    if x_admin_token!=settings.admin_sync_token:raise HTTPException(401,'Invalid admin token')
    teams=_catalog_team_ids()[offset:offset+limit_teams];results=[]
    for name,team_id in teams:
        try:results.append(await sync_team_players(db,name,team_id,download_photos))
        except Exception as e:await db.rollback();results.append({'team':name,'team_id':team_id,'error':type(e).__name__})
    total=(await db.execute(select(func.count(Player.id)))).scalar_one();with_photo=(await db.execute(select(func.count(Player.id)).where(Player.photo_data.is_not(None)))).scalar_one()
    return {'teams_processed':len(results),'offset':offset,'next_offset':offset+len(results),'total_players':total,'players_with_photo':with_photo,'results':results}

async def bootstrap_popular_players()->None:
    """Ensure priority clubs exist even when a previous partial sync left rows in players."""
    from app.database import SessionLocal
    priority=[('Barcelona',529),('Real Madrid',541),('Bayern Munich',157),('Manchester City',50)]
    try:
        async with SessionLocal() as db:
            for name,team_id in priority:
                count=(await db.execute(select(func.count(Player.id)).where(Player.provider=='api-football',Player.team_provider_id==team_id,Player.photo_data.is_not(None)))).scalar_one()
                if count>=10:continue
                try:await sync_team_players(db,name,team_id,True)
                except Exception:await db.rollback()
    except Exception:return
