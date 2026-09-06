import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Team
from app.providers.api_football import APIFootballProvider
from app.providers.sstats import SStatsProvider
from app.providers.uefa import UEFAProvider

router = APIRouter()

async def _proxy(url: str) -> Response:
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            r = await client.get(url, headers={'User-Agent':'guess-the-score/1.0','Accept':'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'})
        ctype=(r.headers.get('content-type') or '').split(';')[0].lower()
        if r.status_code != 200 or not r.content or (ctype and not ctype.startswith('image/') and 'svg' not in ctype):
            raise HTTPException(404, 'Team logo not found')
        return Response(content=r.content, media_type=ctype or 'image/png', headers={'Cache-Control':'public, max-age=604800'})
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, 'Team logo unavailable')

async def _restore_uefa_logo(team: Team, db: AsyncSession) -> str | None:
    if not team.uefa_id:
        return None
    for season_year in (2027, 2026, 2028):
        try:
            rows=await UEFAProvider().competition_teams(1,season_year)
        except Exception:
            continue
        u=next((x for x in rows if x.id==team.uefa_id),None)
        if not u:
            continue
        url=u.logo_medium_url or u.logo_url or u.logo_big_url or u.logo_small_url
        if url:
            team.logo_url=url
            await db.commit()
            return url
    return None

async def _restore_sstats_logo(team: Team, db: AsyncSession) -> str | None:
    if team.provider!='sstats' or not team.provider_id:
        return None
    try:
        payload=await SStatsProvider().get_team(team.provider_id)
    except Exception:
        return None
    rows=payload.get('data') or payload.get('response') or payload
    if isinstance(rows,list):
        row=rows[0] if rows else {}
    elif isinstance(rows,dict):
        row=rows.get('team') if isinstance(rows.get('team'),dict) else rows
    else:
        row={}
    url=row.get('logoUrl') or row.get('LogoUrl') or row.get('logo') or row.get('Logo')
    if isinstance(url,dict):
        url=url.get('url') or url.get('Url')
    if url and str(url).startswith(('http://','https://')):
        team.logo_url=str(url)
        await db.commit()
        return team.logo_url
    return None

def _norm(value: str | None) -> str:
    text=str(value or '').lower()
    for token in ('fc','cf','afc','ac','ssc','us','calcio'):
        text=text.replace(token,' ')
    return ' '.join(text.replace('.',' ').replace('-',' ').split())

async def _restore_api_football_logo(team: Team, db: AsyncSession) -> str | None:
    provider=APIFootballProvider()
    if not provider.settings.api_football_key:
        return None
    query=team.source_name or team.name
    try:
        payload=await provider.search_teams(query)
    except Exception:
        return None
    rows=payload.get('response') or []
    if not isinstance(rows,list):
        return None
    expected=_norm(query)
    chosen=None
    for row in rows:
        candidate=row.get('team') if isinstance(row,dict) else None
        if isinstance(candidate,dict) and _norm(candidate.get('name'))==expected:
            chosen=candidate
            break
    if chosen is None and len(rows)==1 and isinstance(rows[0],dict):
        candidate=rows[0].get('team')
        if isinstance(candidate,dict):
            chosen=candidate
    url=chosen.get('logo') if chosen else None
    if isinstance(url,str) and url.startswith(('http://','https://')):
        team.logo_url=url
        code=chosen.get('code')
        if code and not team.code:
            team.code=str(code)[:20]
        await db.commit()
        return url
    return None

@router.get('/api/team-logo/db/{team_id}', include_in_schema=False)
async def team_logo_by_db_id(team_id: int, db: AsyncSession = Depends(get_db)):
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(404, 'Team not found')
    url=team.logo_url if team.logo_url and team.logo_url.startswith(('http://','https://')) else None
    if not url:
        url=await _restore_sstats_logo(team,db)
    if not url:
        url=await _restore_api_football_logo(team,db)
    if not url:
        url=await _restore_uefa_logo(team,db)
    if not url:
        raise HTTPException(404, 'Team logo not loaded yet')
    try:
        return await _proxy(url)
    except HTTPException:
        fresh=(await _restore_sstats_logo(team,db) or await _restore_api_football_logo(team,db) or await _restore_uefa_logo(team,db))
        if fresh and fresh!=url:
            return await _proxy(fresh)
        raise
