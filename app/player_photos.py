import ipaddress
import socket
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

router = APIRouter(prefix='/api/player-photo', tags=['player-photos'])


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
