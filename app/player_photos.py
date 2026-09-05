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


def _norm(value: str | None) -> str:
    return ' '.join((value or '').casefold().replace('.', ' ').replace('-', ' ').split())


def _team_matches(actual: str | None, expected: str | None) -> bool:
    if not expected:
        return True
    a, e = _norm(actual), _norm(expected)
    if not a or not e:
        return False
    aliases = {
        'барселона': {'barcelona', 'fc barcelona'},
        'бавария': {'bayern munich', 'bayern münchen', 'fc bayern munich'},
        'манчестер сити': {'manchester city', 'man city'},
        'реал мадрид': {'real madrid'},
        'псж': {'paris saint germain', 'paris saint-germain', 'psg'},
        'арсенал': {'arsenal'},
        'атлетико': {'atletico madrid', 'atlético madrid'},
        'ливерпуль': {'liverpool'},
        'интер': {'inter', 'inter milan', 'internazionale'},
    }
    if a == e or a in e or e in a:
        return True
    return a in aliases.get(e, set()) or e in aliases.get(a, set())


def _extract_candidates(payload: dict) -> list[dict]:
    response = payload.get('response') or []
    out = []
    for row in response if isinstance(response, list) else []:
        if not isinstance(row, dict):
            continue
        p = row.get('player') if isinstance(row.get('player'), dict) else row
        pid, name, photo = p.get('id'), p.get('name'), p.get('photo')
        if not pid or not name or not isinstance(photo, str) or not photo.startswith('https://'):
            continue
        stats = row.get('statistics') or []
        team = position = None
        if isinstance(stats, list) and stats:
            first = stats[0] if isinstance(stats[0], dict) else {}
            t = first.get('team') if isinstance(first.get('team'), dict) else {}
            g = first.get('games') if isinstance(first.get('games'), dict) else {}
            team, position = t.get('name'), g.get('position')
        out.append({'id': pid, 'name': str(name), 'photo_src': photo, 'team': team, 'position': position})
    return out


def _translate_position(value: str | None) -> str | None:
    if not value:
        return value
    return {'Goalkeeper':'Вратарь','Defender':'Защитник','Midfielder':'Полузащитник','Attacker':'Нападающий','Forward':'Нападающий','Right Winger':'Нападающий','Left Winger':'Нападающий','Centre-Forward':'Нападающий','Central Midfield':'Полузащитник','Attacking Midfield':'Полузащитник'}.get(value, value)


async def _resolve_thesportsdb(name: str, expected_team: str | None = None) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            r = await client.get('https://www.thesportsdb.com/api/v1/json/123/searchplayers.php', params={'p': name.strip()}, headers={'User-Agent': 'guess-the-score/1.0'})
        if r.status_code != 200:
            return None
        payload = r.json()
    except Exception:
        return None
    rows = payload.get('player') or []
    if not isinstance(rows, list):
        return None
    soccer = [x for x in rows if isinstance(x, dict) and x.get('strPlayer') and (x.get('strSport') or '').casefold() in {'soccer','football'}]
    if not soccer:
        return None
    key = _norm(name)
    exact = [x for x in soccer if _norm(x.get('strPlayer')) == key]
    pool = exact or soccer
    if expected_team:
        by_team = [x for x in pool if _team_matches(x.get('strTeam'), expected_team)]
        if by_team:
            pool = by_team
        else:
            return None
    chosen = pool[0]
    photo = chosen.get('strThumb') or chosen.get('strCutout') or chosen.get('strRender')
    if not isinstance(photo, str) or not photo.startswith('https://'):
        photo = None
    return {'found': bool(photo),'id': chosen.get('idPlayer'),'name': chosen.get('strPlayer') or name,'team': chosen.get('strTeam'),'position': _translate_position(chosen.get('strPosition')),'photo': '/api/player-photo?src=' + quote(photo, safe='') if photo else None,'source': 'thesportsdb'}


@router.get('/resolve', include_in_schema=False)
async def resolve_player_photo(name: str = Query(min_length=3, max_length=100), team: str | None = Query(default=None, max_length=100), user: User = Depends(get_current_user)):
    del user
    key = _norm(name) + '|' + _norm(team)
    cached = _RESOLVE_CACHE.get(key)
    now = time.time()
    if cached and now - cached[0] < _RESOLVE_TTL_SECONDS:
        return cached[1]
    try:
        payload = await APIFootballProvider().search_players(name.strip(), season=2024)
        candidates = _extract_candidates(payload)
    except Exception:
        candidates = []
    if candidates:
        name_key = _norm(name)
        exact = [x for x in candidates if _norm(x['name']) == name_key]
        pool = exact or candidates
        if team:
            by_team = [x for x in pool if _team_matches(x.get('team'), team)]
            if by_team:
                pool = by_team
            else:
                pool = []
        if pool:
            chosen = pool[0]
            result = {'found': True,'id': chosen['id'],'name': chosen['name'],'team': chosen.get('team'),'position': _translate_position(chosen.get('position')),'photo': '/api/player-photo?src=' + quote(chosen['photo_src'], safe=''),'source': 'api-football'}
            _RESOLVE_CACHE[key] = (now, result)
            return result
    fallback = await _resolve_thesportsdb(name, team)
    if fallback:
        if fallback.get('found') or fallback.get('team') or fallback.get('position'):
            _RESOLVE_CACHE[key] = (now, fallback)
        return fallback
    return {'found': False, 'name': name, 'photo': None, 'team': team, 'position': None}


@router.get('', include_in_schema=False)
async def player_photo_proxy(src: str = Query(min_length=8, max_length=1200)):
    url = _public_https_url(src)
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            r = await client.get(url, headers={'User-Agent': 'guess-the-score/1.0'})
        if r.status_code != 200 or not r.content:
            raise HTTPException(404, 'Player photo not found')
        content_type = (r.headers.get('content-type') or '').lower()
        if not content_type.startswith('image/'):
            raise HTTPException(415, 'Player photo response is not an image')
        if len(r.content) > 5 * 1024 * 1024:
            raise HTTPException(413, 'Player photo is too large')
        return Response(content=r.content, media_type=content_type.split(';')[0], headers={'Cache-Control': 'public, max-age=604800'})
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, 'Player photo unavailable')
