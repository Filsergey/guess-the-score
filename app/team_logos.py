import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Team

router = APIRouter()

async def _proxy(url: str) -> Response:
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            r = await client.get(url)
        if r.status_code != 200 or not r.content:
            raise HTTPException(404, 'Team logo not found')
        return Response(content=r.content, media_type=r.headers.get('content-type', 'image/png'), headers={'Cache-Control':'public, max-age=604800'})
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, 'Team logo unavailable')

@router.get('/api/team-logo/db/{team_id}', include_in_schema=False)
async def team_logo_by_db_id(team_id: int, db: AsyncSession = Depends(get_db)):
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(404, 'Team not found')
    if team.logo_url and team.logo_url.startswith(('http://', 'https://')):
        return await _proxy(team.logo_url)
    raise HTTPException(404, 'Team logo not loaded yet')
