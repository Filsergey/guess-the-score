import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Team, Tournament
from app.providers.sstats import SStatsProvider

router = APIRouter()


async def _proxy(url: str) -> Response:
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            r = await client.get(
                url,
                headers={
                    'User-Agent': 'guess-the-score/1.0',
                    'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
                },
            )
        ctype = (r.headers.get('content-type') or '').split(';')[0].lower()
        if r.status_code != 200 or not r.content or (
            ctype and not ctype.startswith('image/') and 'svg' not in ctype
        ):
            raise HTTPException(404, 'Logo not found')
        return Response(
            content=r.content,
            media_type=ctype or 'image/png',
            headers={'Cache-Control': 'public, max-age=604800'},
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, 'Logo unavailable')


async def _restore_sstats_logo(team: Team, db: AsyncSession) -> str | None:
    if team.provider != 'sstats' or not team.provider_id:
        return None
    try:
        payload = await SStatsProvider().get_team(team.provider_id)
    except Exception:
        return None
    rows = payload.get('data') or payload.get('response') or payload
    if isinstance(rows, list):
        row = rows[0] if rows else {}
    elif isinstance(rows, dict):
        row = rows.get('team') if isinstance(rows.get('team'), dict) else rows
    else:
        row = {}
    url = row.get('logoUrl') or row.get('LogoUrl') or row.get('logo') or row.get('Logo')
    if isinstance(url, dict):
        url = url.get('url') or url.get('Url')
    if url and str(url).startswith(('http://', 'https://')):
        team.logo_url = str(url)
        await db.commit()
        return team.logo_url
    return None


@router.get('/api/team-logo/db/{team_id}', include_in_schema=False)
async def team_logo_by_db_id(team_id: int, db: AsyncSession = Depends(get_db)):
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(404, 'Team not found')

    url = team.logo_url if team.logo_url and team.logo_url.startswith(('http://', 'https://')) else None
    if not url:
        url = await _restore_sstats_logo(team, db)
    if not url:
        raise HTTPException(404, 'Team logo not loaded yet')

    try:
        return await _proxy(url)
    except HTTPException:
        fresh = await _restore_sstats_logo(team, db)
        if fresh and fresh != url:
            return await _proxy(fresh)
        raise


@router.get('/api/tournament-logo/db/{tournament_id}', include_in_schema=False)
async def tournament_logo_by_db_id(tournament_id: int, db: AsyncSession = Depends(get_db)):
    tournament = await db.get(Tournament, tournament_id)
    if not tournament:
        raise HTTPException(404, 'Tournament not found')
    url = tournament.logo_url if tournament.logo_url and tournament.logo_url.startswith(('http://', 'https://')) else None
    if not url:
        raise HTTPException(404, 'Tournament logo not loaded yet')
    return await _proxy(url)
