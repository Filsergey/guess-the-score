from urllib.parse import unquote

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.localization import API_FOOTBALL_TEAM_IDS, normalize_team_name
from app.models import Team
from app.providers.api_football import APIFootballProvider

router = APIRouter()


def _safe_search_name(value: str) -> str:
    cleaned = ''.join(ch if (ch.isalnum() or ch.isspace()) else ' ' for ch in value)
    return ' '.join(cleaned.split())


def _pick_team(payload: dict, expected_name: str) -> dict | None:
    rows = payload.get('response') or []
    if not isinstance(rows, list):
        return None
    expected = normalize_team_name(expected_name)
    for row in rows:
        team = row.get('team') if isinstance(row, dict) else None
        if isinstance(team, dict) and normalize_team_name(team.get('name')) == expected:
            return team
    if len(rows) == 1 and isinstance(rows[0], dict) and isinstance(rows[0].get('team'), dict):
        return rows[0]['team']
    return None


async def _proxy(url: str) -> Response:
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            r = await client.get(url)
        if r.status_code != 200 or not r.content:
            raise HTTPException(404, 'Team logo not found')
        return Response(
            content=r.content,
            media_type=r.headers.get('content-type', 'image/png'),
            headers={'Cache-Control': 'public, max-age=604800'},
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, 'Team logo unavailable')


@router.get('/api/team-logo/db/{team_id}', include_in_schema=False)
async def team_logo_by_db_id(team_id: int, db: AsyncSession = Depends(get_db)):
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(404, 'Team not found')

    # Existing stored image is always preferred. It may come from API-Football
    # or from a previous dynamic resolution.
    if team.logo_url and team.logo_url.startswith(('http://', 'https://')):
        return await _proxy(team.logo_url)

    # Known clubs are resolved without spending an API request.
    known_id = API_FOOTBALL_TEAM_IDS.get(team.name)
    if known_id is not None:
        return await _proxy(f'https://media.api-sports.io/football/teams/{known_id}.png')

    # Any other club is resolved by name once and persisted in the DB. This
    # covers qualifiers/new clubs too, so we no longer need a hand-written list.
    query = _safe_search_name(team.name)
    if len(query) < 3:
        raise HTTPException(404, 'Team logo not found')
    try:
        payload = await APIFootballProvider().search_teams(query)
        found = _pick_team(payload, team.name)
        logo = found.get('logo') if found else None
        if not isinstance(logo, str) or not logo.startswith(('http://', 'https://')):
            raise HTTPException(404, 'Team logo not found')
        team.logo_url = logo
        code = found.get('code') if found else None
        if code and not team.code:
            team.code = str(code)[:20]
        await db.commit()
        return await _proxy(logo)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, 'Team logo lookup unavailable')
