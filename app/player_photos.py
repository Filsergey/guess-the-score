import ipaddress
import socket
import time
from urllib.parse import quote, urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.auth import get_current_user
from app.localization import API_FOOTBALL_TEAM_IDS, TEAM_NAMES_RU
from app.models import User
from app.providers.api_football import APIFootballProvider

router = APIRouter(prefix='/api/player-photo', tags=['player-photos'])

_RESOLVE_CACHE: dict[str, tuple[float, dict]] = {}
_RESOLVE_TTL_SECONDS = 24 * 60 * 60
_SQUAD_CACHE: dict[int, tuple[float, list[dict]]] = {}
_SQUAD_TTL_SECONDS = 6 * 60 * 60


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
        'real madrid': {'реал мадрид'},
        'пари сен жермен': {'paris saint germain', 'paris saint-germain', 'psg'},
        'псж': {'paris saint germain', 'paris saint-germain', 'psg'},
        'арсенал': {'arsenal'},
        'атлетико': {'atletico madrid', 'atlético madrid'},
        'ливерпуль': {'liverpool'},
        'интер': {'inter', 'inter milan', 'internazionale'},
    }
    if a == e or a in e or e in a:
        return True
    return a in aliases.get(e, set()) or e in aliases.get(a, set())


def _team_id_for_name(name: str | None) -> int | None:
    if not name:
        return None
    target = _norm(name)
    for english, team_id in API_FOOTBALL_TEAM_IDS.items():
        if _norm(english) == target:
            return team_id
        ru = TEAM_NAMES_RU.get(english)
        if ru and _norm(ru) == target:
            return team_id
    return {
        'бавария': 157, 'барселона': 529, 'манчестер сити': 50,
        'реал мадрид': 541, 'псж': 85, 'пари сен жермен': 85,
        'арсенал': 42, 'атлетико': 530, 'ливерпуль': 40, 'интер': 505,
    }.get(target)


def _translate_position(value: str | None) -> str | None:
    if not value:
        return value
    return {
        'Goalkeeper': 'Вратарь', 'Defender': 'Защитник', 'Midfielder': 'Полузащитник',
        'Attacker': 'Нападающий', 'Forward': 'Нападающий', 'Right Winger': 'Нападающий',
        'Left Winger': 'Нападающий', 'Centre-Forward': 'Нападающий',
        'Central Midfield': 'Полузащитник', 'Attacking Midfield': 'Полузащитник',
    }.get(value, value)


async def _current_squad(team_id: int) -> list[dict]:
    now = time.time()
    cached = _SQUAD_CACHE.get(team_id)
    if cached and now - cached[0] < _SQUAD_TTL_SECONDS:
        return cached[1]
    payload = await APIFootballProvider().get_squad(team_id)
    rows = payload.get('response') or []
    players: list[dict] = []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            raw_players = row.get('players') or []
            if not isinstance(raw_players, list):
                continue
            for p in raw_players:
                if not isinstance(p, dict) or not p.get('name'):
                    continue
                players.append({
                    'id': p.get('id'),
                    'name': str(p.get('name')),
                    'position': _translate_position(p.get('position')),
                    'photo_src': p.get('photo') if isinstance(p.get('photo'), str) else None,
                })
    _SQUAD_CACHE[team_id] = (now, players)
    return players


async def _resolve_from_squad(name: str, team: str) -> dict | None:
    team_id = _team_id_for_name(team)
    if not team_id:
        return None
    try:
        players = await _current_squad(team_id)
    except Exception:
        return None
    key = _norm(name)
    exact = [p for p in players if _norm(p.get('name')) == key]
    if not exact:
        exact = [p for p in players if key in _norm(p.get('name')) or _norm(p.get('name')) in key]
    if not exact:
        return None
    p = exact[0]
    photo = p.get('photo_src')
    return {
        'found': bool(photo), 'id': p.get('id'), 'name': p.get('name') or name,
        'team': team, 'position': p.get('position'),
        'photo': '/api/player-photo?src=' + quote(photo, safe='') if photo and photo.startswith('https://') else None,
        'source': 'api-football-squad',
    }


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


@router.get('/resolve', include_in_schema=False)
async def resolve_player_photo(name: str = Query(min_length=3, max_length=100), team: str | None = Query(default=None, max_length=100), user: User = Depends(get_current_user)):
    del user
    key = _norm(name) + '|' + _norm(team)
    cached = _RESOLVE_CACHE.get(key)
    now = time.time()
    if cached and now - cached[0] < _RESOLVE_TTL_SECONDS:
        return cached[1]

    if team:
        squad = await _resolve_from_squad(name, team)
        if squad:
            _RESOLVE_CACHE[key] = (now, squad)
            return squad

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
            pool = [x for x in pool if _team_matches(x.get('team'), team)]
        if pool:
            chosen = pool[0]
            result = {
                'found': True, 'id': chosen['id'], 'name': chosen['name'],
                'team': chosen.get('team') or team,
                'position': _translate_position(chosen.get('position')),
                'photo': '/api/player-photo?src=' + quote(chosen['photo_src'], safe=''),
                'source': 'api-football-search',
            }
            _RESOLVE_CACHE[key] = (now, result)
            return result

    return {'found': False, 'name': name, 'photo': None, 'team': team, 'position': None}


@router.get('', include_in_schema=False)
async def player_photo_proxy(src: str = Query(min_length=8, max_length=1200)):
    url = _public_https_url(src)
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            r = await client.get(url, headers={'User-Agent': 'guess-the-score/1.0'})
        if r.status_code != 200 or not r.content:
            raise HTTPException(404, 'Player photo not found')
        content_type = (r.headers.get('content-type') or '').lower()
        if not content_type.startswith('image/'):
            raise HTTPException(415, 'Player photo response is not an image')
        if len(r.content) > 5 * 1024 * 1024:
            raise HTTPException(413, 'Player photo is too large')
        return Response(content=r.content, media_type=content_type.split(';')[0], headers={'Cache-Control': 'public, max-age=604800, immutable'})
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, 'Player photo unavailable')
