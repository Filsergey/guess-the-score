import ipaddress
import socket
import time
from urllib.parse import quote, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.auth import get_current_user
from app.models import User
from app.providers.api_football import APIFootballProvider

router = APIRouter(prefix='/api/player-photo', tags=['player-photos'])

# Small in-process cache prevents repeated API-Football lookups when the same
# saved tournament prediction is opened multiple times.
_RESOLVE_CACHE: dict[str, tuple[float, dict]] = {}
_RESOLVE_TTL_SECONDS = 24 * 60 * 60


def _public_https_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != 'https' or not parsed.hostname:
        raise HTTPException(400, 'Invalid player photo URL')
    host = parsed.hostname.lower()
    if host in {'localhost'}:
        raise HTTPException(400, 'Invalid player photo host')
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise HTTPException(404, 'Player photo host not found')
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise HTTPException(400, 'Invalid player photo host')
    return value


def _norm(value: str) -> str:
    return ' '.join(value.casefold().replace('.', ' ').replace('-', ' ').split())


def _extract_candidates(payload: dict) -> list[dict]:
    response = payload.get('response') or []
    out = []
    for row in response if isinstance(response, list) else []:
        if not isinstance(row, dict):
            continue
        p = row.get('player') if isinstance(row.get('player'), dict) else row
        pid = p.get('id')
        name = p.get('name')
        photo = p.get('photo')
        if not pid or not name or not isinstance(photo, str) or not photo.startswith('https://'):
            continue
        stats = row.get('statistics') or []
        team = None
        position = None
        if isinstance(stats, list) and stats:
            first = stats[0] if isinstance(stats[0], dict) else {}
            t = first.get('team') if isinstance(first.get('team'), dict) else {}
            g = first.get('games') if isinstance(first.get('games'), dict) else {}
            team = t.get('name')
            position = g.get('position')
        out.append({'id': pid, 'name': str(name), 'photo_src': photo, 'team': team, 'position': position})
    return out


@router.get('/resolve', include_in_schema=False)
async def resolve_player_photo(
    name: str = Query(min_length=3, max_length=100),
    user: User = Depends(get_current_user),
):
    del user
    key = _norm(name)
    cached = _RESOLVE_CACHE.get(key)
    now = time.time()
    if cached and now - cached[0] < _RESOLVE_TTL_SECONDS:
        return cached[1]

    try:
        payload = await APIFootballProvider().search_players(name.strip(), season=2024)
    except Exception:
        result = {'found': False, 'name': name, 'photo': None}
        _RESOLVE_CACHE[key] = (now, result)
        return result

    candidates = _extract_candidates(payload)
    if not candidates:
        result = {'found': False, 'name': name, 'photo': None}
        _RESOLVE_CACHE[key] = (now, result)
        return result

    exact = [x for x in candidates if _norm(x['name']) == key]
    chosen = exact[0] if exact else candidates[0]
    result = {
        'found': True,
        'id': chosen['id'],
        'name': chosen['name'],
        'team': chosen.get('team'),
        'position': chosen.get('position'),
        'photo': '/api/player-photo?src=' + quote(chosen['photo_src'], safe=''),
    }
    _RESOLVE_CACHE[key] = (now, result)
    return result


@router.get('', include_in_schema=False)
async def player_photo_proxy(src: str = Query(min_length=8, max_length=1200)):
    url = _public_https_url(src)
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            r = await client.get(url, headers={'User-Agent': 'guess-the-score/1.0'})
        if r.status_code != 200 or not r.content:
            raise HTTPException(404, 'Player photo not found')
        content_type = (r.headers.get('content-type') or '').lower()
        if not content_type.startswith('image/'):
            raise HTTPException(415, 'Player photo response is not an image')
        if len(r.content) > 5 * 1024 * 1024:
            raise HTTPException(413, 'Player photo is too large')
        return Response(
            content=r.content,
            media_type=content_type.split(';')[0],
            headers={'Cache-Control': 'public, max-age=604800'},
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, 'Player photo unavailable')
