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
from app.localization import team_name_ru
from app.models import Player, User
from app.providers.api_football import APIFootballProvider
from app.providers.uefa import UEFAProvider, UEFATeam

router = APIRouter(tags=['players'])
settings = get_settings()

POPULAR_NAMES = {
    'Kylian Mbappe','Harry Kane','Erling Haaland','Lamine Yamal','Vinicius Junior','Ousmane Dembele',
    'Bukayo Saka','Raphinha','Julian Alvarez','Jude Bellingham','Pedri','Florian Wirtz','Jamal Musiala','Lautaro Martinez'
}
POPULAR_TOKENS = ('mbappe','kane','haaland','yamal','vinicius','dembele','saka','raphinha','alvarez','bellingham','pedri','wirtz','musiala','lautaro')

POSITION_RU = {
    'Goalkeeper':'Вратарь','Defender':'Защитник','Midfielder':'Полузащитник','Attacker':'Нападающий',
    'Forward':'Нападающий','Right Winger':'Нападающий','Left Winger':'Нападающий','Centre-Forward':'Нападающий',
    'Central Midfield':'Полузащитник','Attacking Midfield':'Полузащитник','Defensive Midfield':'Полузащитник',
    'Right-Back':'Защитник','Left-Back':'Защитник','Centre-Back':'Защитник'
}


def _position_ru(value: str | None) -> str | None:
    return POSITION_RU.get(value or '', value)


def _is_popular(name: str) -> bool:
    low = name.casefold()
    return name in POPULAR_NAMES or any(token in low for token in POPULAR_TOKENS)


async def _download_photo(client:httpx.AsyncClient,url:str|None)->tuple[bytes|None,str|None]:
    if not url or not url.startswith('https://'):
        return None,None
    try:
        r=await client.get(url,headers={'User-Agent':'guess-the-score/1.0'})
        ctype=(r.headers.get('content-type') or '').split(';')[0].lower()
        if r.status_code==200 and r.content and ctype.startswith('image/') and len(r.content)<=2*1024*1024:
            return r.content,ctype
    except Exception:
        pass
    return None,None


async def sync_uefa_team_players(
    db:AsyncSession,
    team:UEFATeam,
    season_year:int=2027,
    download_photos:bool=True,
)->dict:
    provider=UEFAProvider()
    rows,diagnostic=await provider.squad(team.id)
    ids=[row.id for row in rows]
    existing_rows=(
        await db.execute(select(Player).where(Player.provider=='uefa',Player.provider_id.in_(ids)))
    ).scalars().all() if ids else []
    existing={p.provider_id:p for p in existing_rows}

    photo_results:list[tuple[bytes|None,str|None]]=[]
    if rows and download_photos:
        async with httpx.AsyncClient(timeout=10.0,follow_redirects=True,limits=httpx.Limits(max_connections=8)) as client:
            sem=asyncio.Semaphore(6)
            async def dl(row):
                async with sem:
                    return await _download_photo(client,row.photo_url)
            photo_results=await asyncio.gather(*(dl(row) for row in rows))
    else:
        photo_results=[(None,None) for _ in rows]

    now=datetime.now(timezone.utc)
    saved=photos=with_photo_url=0
    active_ids=set(ids)
    for idx,row in enumerate(rows):
        player=existing.get(row.id)
        if not player:
            player=Player(provider='uefa',provider_id=row.id,name=row.name)
            db.add(player)
        player.name=row.name
        player.display_name=row.name
        player.team_provider_id=team.id
        player.team_name=team.name
        player.position=_position_ru(row.position)
        player.shirt_number=row.number
        player.nationality=row.nationality
        player.photo_source_url=row.photo_url
        player.has_photo=bool(row.photo_url or player.photo_data)
        player.is_active=True
        player.is_popular=_is_popular(row.name)
        player.season=season_year
        player.updated_at=now
        if row.photo_url:
            with_photo_url+=1
        if idx<len(photo_results):
            data,ctype=photo_results[idx]
            if data:
                player.photo_data=data
                player.photo_media_type=ctype
                player.has_photo=True
                photos+=1
        saved+=1

    # Players removed from the current UEFA squad remain in the catalogue for
    # history, but are not offered as active picks for this club/season.
    if active_ids:
        stale=(
            await db.execute(
                select(Player).where(
                    Player.provider=='uefa',
                    Player.team_provider_id==team.id,
                    Player.is_active.is_(True),
                    Player.provider_id.not_in(active_ids),
                )
            )
        ).scalars().all()
        for player in stale:
            player.is_active=False
            player.updated_at=now

    await db.commit()
    return {
        'provider':'uefa',
        'team':team.name,
        'team_ru':team.name_ru,
        'team_id':team.id,
        'received':len(rows),
        'saved':saved,
        'photo_urls':with_photo_url,
        'photos_downloaded':photos,
        'diagnostic':diagnostic,
    }


async def _player_rows(db:AsyncSession,q:str|None,popular:bool,limit:int):
    cols=(
        Player.id,Player.provider,Player.provider_id,Player.name,Player.display_name,Player.team_name,
        Player.position,Player.shirt_number,Player.nationality,Player.is_popular,Player.photo_source_url,
        (Player.photo_data.is_not(None)).label('has_photo_blob')
    )
    base=select(*cols).where(Player.is_active.is_(True))
    if q:
        like=f"%{q.strip()}%"
        base=base.where(or_(Player.name.ilike(like),Player.display_name.ilike(like),Player.team_name.ilike(like)))
    if popular:
        rows=(await db.execute(base.where(Player.is_popular.is_(True)).order_by(Player.name).limit(limit))).all()
        if rows:
            return rows
        return (await db.execute(base.order_by(Player.name).limit(limit))).all()
    return (await db.execute(base.order_by(Player.is_popular.desc(),Player.name).limit(limit))).all()


@router.get('/api/players')
async def list_players(
    q:str|None=Query(default=None,max_length=100),
    popular:bool=Query(default=False),
    limit:int=Query(default=30,ge=1,le=100),
    user:User=Depends(get_current_user),
    db:AsyncSession=Depends(get_db),
):
    del user
    rows=await _player_rows(db,q,popular,limit)
    return {
        'count':len(rows),
        'response':[
            {
                'id':r.id,
                'provider':r.provider,
                'provider_id':r.provider_id,
                'name':r.name,
                'display_name':r.display_name or r.name,
                'team':team_name_ru(r.team_name) if r.team_name else None,
                'team_original':r.team_name,
                'position':r.position,
                'number':r.shirt_number,
                'nationality':r.nationality,
                'photo':f'/api/players/{r.id}/photo' if (r.has_photo_blob or r.photo_source_url) else None,
                'has_photo':bool(r.has_photo_blob or r.photo_source_url),
                'popular':r.is_popular,
            }
            for r in rows
        ],
    }


@router.get('/api/players/catalog-status',include_in_schema=False)
async def player_catalog_status(db:AsyncSession=Depends(get_db)):
    total=(await db.execute(select(func.count(Player.id)))).scalar_one()
    active=(await db.execute(select(func.count(Player.id)).where(Player.is_active.is_(True)))).scalar_one()
    with_blob=(await db.execute(select(func.count(Player.id)).where(Player.photo_data.is_not(None)))).scalar_one()
    with_source=(await db.execute(select(func.count(Player.id)).where(Player.photo_source_url.is_not(None)))).scalar_one()
    popular=(await db.execute(select(func.count(Player.id)).where(Player.is_popular.is_(True)))).scalar_one()
    uefa=(await db.execute(select(func.count(Player.id)).where(Player.provider=='uefa'))).scalar_one()
    return {'total':total,'active':active,'uefa':uefa,'with_photo_blob':with_blob,'with_photo_source':with_source,'popular':popular}


@router.get('/api/players/uefa-check',include_in_schema=False)
async def uefa_provider_check(team_id:int=Query(default=50080,ge=1)):
    """Safe diagnostic for the UEFA squad scraper. No credentials are used."""
    try:
        rows,diagnostic=await UEFAProvider().squad(team_id)
    except Exception as e:
        return {'ok':False,'team_id':team_id,'error':type(e).__name__,'message':str(e)[:300]}
    return {
        'ok':bool(rows),
        'team_id':team_id,
        **diagnostic,
        'players':len(rows),
        'with_photo':sum(1 for row in rows if row.photo_url),
        'sample':[
            {
                'id':row.id,'name':row.name,'number':row.number,'nationality':row.nationality,
                'position':row.position,'photo':row.photo_url,'profile':row.profile_url,
            }
            for row in rows[:8]
        ],
        'note':None if rows else 'UEFA returned HTML without rendered player rows; inspect XHR/hydration endpoint if this persists.',
    }


@router.get('/api/players/provider-check',include_in_schema=False)
async def legacy_api_football_provider_check(team_id:int=Query(default=529,ge=1)):
    """Temporary legacy diagnostic kept while API-Football is suspended."""
    try:
        payload=await APIFootballProvider().get_squad(team_id)
    except Exception as e:
        return {'ok':False,'team_id':team_id,'error':type(e).__name__,'message':str(e)[:240]}
    response=payload.get('response') or []
    if not response:
        return {'ok':True,'team_id':team_id,'response_count':0,'players':0,'with_photo':0,'sample':[]}
    root=response[0] if isinstance(response[0],dict) else {}
    team=root.get('team') if isinstance(root.get('team'),dict) else {}
    rows=root.get('players') or []
    rows=rows if isinstance(rows,list) else []
    sample=[];with_photo=0
    for row in rows:
        if not isinstance(row,dict):
            continue
        photo=row.get('photo');has=bool(isinstance(photo,str) and photo.startswith('http'))
        if has:
            with_photo+=1
        if len(sample)<8:
            sample.append({'id':row.get('id'),'name':row.get('name'),'position':row.get('position'),'has_photo':has,'photo':photo if has else None})
    return {'ok':True,'team_id':team_id,'team':team.get('name'),'response_count':len(response),'players':len(rows),'with_photo':with_photo,'sample':sample}


@router.get('/api/players/{player_id}/photo',include_in_schema=False)
async def player_photo_from_db(player_id:int,db:AsyncSession=Depends(get_db)):
    player=await db.get(Player,player_id)
    if not player:
        raise HTTPException(404,'Player not found')
    if player.photo_data:
        return Response(
            content=player.photo_data,
            media_type=player.photo_media_type or 'image/jpeg',
            headers={'Cache-Control':'public, max-age=604800, immutable'},
        )
    if player.photo_source_url:
        async with httpx.AsyncClient(timeout=8.0,follow_redirects=True) as client:
            data,ctype=await _download_photo(client,player.photo_source_url)
        if data:
            player.photo_data=data
            player.photo_media_type=ctype
            player.has_photo=True
            await db.commit()
            return Response(
                content=data,
                media_type=ctype or 'image/jpeg',
                headers={'Cache-Control':'public, max-age=604800, immutable'},
            )
    raise HTTPException(404,'Player photo not found in database')


@router.post('/api/admin/players/sync')
async def sync_players_catalog(
    limit_teams:int=Query(default=5,ge=1,le=36),
    offset:int=Query(default=0,ge=0),
    download_photos:bool=Query(default=True),
    competition_id:int=Query(default=1,ge=1),
    season_year:int=Query(default=2027,ge=2000,le=2100),
    x_admin_token:str|None=Header(default=None),
    db:AsyncSession=Depends(get_db),
):
    if not settings.admin_sync_token:
        raise HTTPException(503,'ADMIN_SYNC_TOKEN is not configured')
    if x_admin_token!=settings.admin_sync_token:
        raise HTTPException(401,'Invalid admin token')

    try:
        all_teams=await UEFAProvider().competition_teams(competition_id,season_year)
    except Exception as e:
        raise HTTPException(502,f'UEFA standings error: {type(e).__name__}: {str(e)[:180]}') from e

    teams=all_teams[offset:offset+limit_teams]
    results=[]
    for team in teams:
        try:
            results.append(await sync_uefa_team_players(db,team,season_year,download_photos))
        except Exception as e:
            await db.rollback()
            results.append({'provider':'uefa','team':team.name,'team_id':team.id,'error':type(e).__name__,'message':str(e)[:180]})

    total=(await db.execute(select(func.count(Player.id)).where(Player.provider=='uefa'))).scalar_one()
    with_photo=(await db.execute(select(func.count(Player.id)).where(Player.provider=='uefa',Player.photo_data.is_not(None)))).scalar_one()
    return {
        'provider':'uefa',
        'competition_id':competition_id,
        'season_year':season_year,
        'teams_available':len(all_teams),
        'teams_processed':len(results),
        'offset':offset,
        'next_offset':offset+len(results),
        'total_players':total,
        'players_with_photo':with_photo,
        'results':results,
    }


async def bootstrap_popular_players()->None:
    """Best-effort bootstrap of the four most useful clubs after deployment.

    It only fills metadata/photo URLs; image bytes are downloaded lazily by the
    photo endpoint or by the explicit admin sync, keeping startup lightweight.
    """
    from app.database import SessionLocal

    priority=[
        UEFATeam(50080,'Barcelona','Барселона','ESP',None),
        UEFATeam(50051,'Real Madrid','Реал','ESP',None),
        UEFATeam(50037,'Bayern München','Бавария','GER',None),
        UEFATeam(52919,'Man City','Ман Сити','ENG',None),
    ]
    try:
        async with SessionLocal() as db:
            for team in priority:
                count=(await db.execute(select(func.count(Player.id)).where(Player.provider=='uefa',Player.team_provider_id==team.id,Player.is_active.is_(True)))).scalar_one()
                with_source=(await db.execute(select(func.count(Player.id)).where(Player.provider=='uefa',Player.team_provider_id==team.id,Player.photo_source_url.is_not(None)))).scalar_one()
                if count>=10 and with_source>=10:
                    continue
                try:
                    await sync_uefa_team_players(db,team,2027,False)
                except Exception:
                    await db.rollback()
    except Exception:
        return
