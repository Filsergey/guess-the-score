import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Team
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
    """Restore an official UEFA logo if a mapped team has an empty/stale logo_url."""
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

@router.get('/api/team-logo/db/{team_id}', include_in_schema=False)
async def team_logo_by_db_id(team_id: int, db: AsyncSession = Depends(get_db)):
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(404, 'Team not found')
    url=team.logo_url if team.logo_url and team.logo_url.startswith(('http://','https://')) else None
    if not url:
        url=await _restore_uefa_logo(team,db)
    if not url:
        raise HTTPException(404, 'Team logo not loaded yet')
    try:
        return await _proxy(url)
    except HTTPException:
        # UEFA occasionally changes a stored image URL. Refresh it once from standings.
        fresh=await _restore_uefa_logo(team,db)
        if fresh and fresh!=url:
            return await _proxy(fresh)
        raise
