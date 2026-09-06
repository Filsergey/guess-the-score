import asyncio
from datetime import datetime, timezone
from time import monotonic

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models import LeagueMember, Tournament, User, UserLeague
from app.providers.sstats import SStatsProvider
from app.services.competition_readiness import prepare_sstats_competition_tolerant

router = APIRouter(prefix="/api/leagues", tags=["league-catalog"])

TOP_TOURNAMENTS = (
    {"league_id": 2, "name": "UEFA Champions League", "country": "Europe"},
    {"league_id": 39, "name": "Premier League", "country": "England"},
    {"league_id": 140, "name": "La Liga", "country": "Spain"},
    {"league_id": 78, "name": "Bundesliga", "country": "Germany"},
    {"league_id": 135, "name": "Serie A", "country": "Italy"},
    {"league_id": 61, "name": "Ligue 1", "country": "France"},
    {"league_id": 88, "name": "Eredivisie", "country": "Netherlands"},
    {"league_id": 71, "name": "Serie A", "country": "Brazil"},
    {"league_id": 94, "name": "Primeira Liga", "country": "Portugal"},
    {"league_id": 262, "name": "Liga MX", "country": "Mexico"},
    {"league_id": 235, "name": "Russian Premier League", "country": "Russia"},
)
ALLOWED_TOURNAMENTS = {item["league_id"]: item for item in TOP_TOURNAMENTS}
TOURNAMENT_LOGO_IDS = set(ALLOWED_TOURNAMENTS)

# SStats remains the only external logo source. These are local, generated fallbacks
# so a temporarily missing SStats badge never turns every league icon into the same ball.
TOURNAMENT_FALLBACKS = {
    2: ("UCL", "#07182e", "#20a7ff"),
    39: ("PL", "#37003c", "#04f5ff"),
    140: ("LL", "#171717", "#ff4655"),
    78: ("BL", "#ffffff", "#d20515"),
    135: ("A", "#ffffff", "#0068ff"),
    61: ("L1", "#071a38", "#ee1747"),
    88: ("ERE", "#ffffff", "#e31b23"),
    71: ("BR", "#0b6b3a", "#ffd400"),
    94: ("PT", "#0b6b3a", "#d71920"),
    262: ("MX", "#0b6b3a", "#d71920"),
    235: ("RPL", "#143d8d", "#e53935"),
}
_LOGO_CACHE: dict[int, str | None] = {}
_LOGO_CACHE_AT = 0.0
_LOGO_CACHE_TTL = 600.0
_LOGO_CACHE_LOCK = asyncio.Lock()


class CatalogSyncBody(BaseModel):
    league_id: int = Field(ge=1)
    year: int = Field(ge=2020, le=2100)
    league_name: str | None = Field(default=None, max_length=200)


class LeagueThemeBody(BaseModel):
    icon: str | None = Field(default=None, max_length=900000)
    background: str | None = Field(default=None, max_length=1800000)
    tournament_background: str | None = Field(default=None, max_length=1200000)


def _catalog_seasons() -> list[dict]:
    now = datetime.now(timezone.utc)
    current = now.year if now.month >= 7 else now.year - 1
    return [{"year": year, "uid": None} for year in range(current, 2019, -1)]


def _upstream_error_message(exc: Exception) -> str:
    base = str(exc).strip() or type(exc).__name__
    current = exc
    seen = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, httpx.HTTPStatusError):
            status = current.response.status_code
            reason = current.response.reason_phrase or "HTTP error"
            if status == 429:
                return "SStats HTTP 429 Too Many Requests"
            return f"SStats HTTP {status} {reason}"
        current = current.__cause__ or current.__context__
    return base


async def _theme_league(league_id: int, user: User, db: AsyncSession) -> UserLeague:
    league = await db.get(UserLeague, league_id)
    if league is None:
        raise HTTPException(404, "League not found")
    if user.role != "superadmin":
        member = await db.scalar(
            select(LeagueMember.id).where(
                LeagueMember.league_id == league_id,
                LeagueMember.user_id == user.id,
            )
        )
        if member is None:
            raise HTTPException(403, "You are not a member of this league")
    return league


def _theme_response(league: UserLeague) -> dict:
    return {
        "league_id": league.id,
        "icon": league.theme_icon,
        "background": league.theme_background,
        "tournament_background": league.theme_tournament_background,
    }


def _logo_value(row: dict):
    logo = row.get("logoUrl") or row.get("LogoUrl") or row.get("logo") or row.get("Logo")
    if isinstance(logo, dict):
        logo = logo.get("url") or logo.get("Url")
    return str(logo) if logo and str(logo).startswith(("http://", "https://")) else None


def _fallback_tournament_logo_response(provider_id: int | None) -> Response:
    code, background, accent = TOURNAMENT_FALLBACKS.get(provider_id, ("T", "#10263b", "#24a4ff"))
    font_size = 25 if len(code) == 1 else 19 if len(code) == 2 else 14
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
<rect width="96" height="96" rx="24" fill="{background}"/>
<circle cx="48" cy="48" r="38" fill="none" stroke="{accent}" stroke-width="5"/>
<circle cx="48" cy="48" r="30" fill="none" stroke="{accent}" stroke-opacity=".28" stroke-width="2"/>
<path d="M25 65 C39 76 57 76 71 65" fill="none" stroke="{accent}" stroke-width="4" stroke-linecap="round"/>
<text x="48" y="55" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-size="{font_size}" font-weight="800" fill="{accent}">{code}</text>
</svg>'''
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=604800, stale-while-revalidate=2592000"},
    )


async def _load_sstats_tournament_logo_cache() -> None:
    global _LOGO_CACHE_AT
    now = monotonic()
    if _LOGO_CACHE and now - _LOGO_CACHE_AT < _LOGO_CACHE_TTL:
        return
    async with _LOGO_CACHE_LOCK:
        now = monotonic()
        if _LOGO_CACHE and now - _LOGO_CACHE_AT < _LOGO_CACHE_TTL:
            return
        logos = {provider_id: None for provider_id in TOURNAMENT_LOGO_IDS}
        try:
            payload = await SStatsProvider().get_leagues()
            rows = payload.get("data") or payload.get("response") or []
            if isinstance(rows, dict):
                rows = [rows]
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    raw_id = row.get("id") or row.get("Id") or row.get("leagueId") or row.get("LeagueId")
                    try:
                        provider_id = int(raw_id)
                    except (TypeError, ValueError):
                        continue
                    if provider_id in logos:
                        logos[provider_id] = _logo_value(row)
        except Exception:
            pass
        _LOGO_CACHE.clear()
        _LOGO_CACHE.update(logos)
        _LOGO_CACHE_AT = monotonic()


async def _sstats_tournament_logo_url(provider_id: int) -> str | None:
    await _load_sstats_tournament_logo_cache()
    return _LOGO_CACHE.get(int(provider_id))


@router.get("/tournament-logo/{provider_id}")
async def tournament_logo(provider_id: int):
    """Serve the SStats tournament badge, with a local non-network fallback."""
    if provider_id not in TOURNAMENT_LOGO_IDS:
        raise HTTPException(404, "Tournament logo not configured")
    url = await _sstats_tournament_logo_url(provider_id)
    if url:
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                upstream = await client.get(url, headers={"User-Agent": "guess-the-score/1.0"})
                upstream.raise_for_status()
            content_type = upstream.headers.get("content-type") or "image/png"
            return Response(
                content=upstream.content,
                media_type=content_type.split(";", 1)[0],
                headers={"Cache-Control": "public, max-age=86400, stale-while-revalidate=604800"},
            )
        except Exception:
            pass
    return _fallback_tournament_logo_response(provider_id)


@router.get("/catalog")
async def tournament_catalog(user: User = Depends(get_current_user)):
    del user
    seasons = _catalog_seasons()
    response = [
        {
            **item,
            "logo_url": f"/api/leagues/tournament-logo/{item['league_id']}",
            "seasons": [dict(season) for season in seasons],
        }
        for item in TOP_TOURNAMENTS
    ]
    return {"count": len(response), "response": response, "source": "fixed-top-tournaments"}


@router.get("/catalog/logo-check")
async def tournament_logo_check():
    return {
        "source": "sstats-with-local-fallback",
        "count": len(TOP_TOURNAMENTS),
        "matches": [
            {
                "league_id": item["league_id"],
                "name": item["name"],
                "country": item["country"],
                "logo_url": f"/api/leagues/tournament-logo/{item['league_id']}",
            }
            for item in TOP_TOURNAMENTS
        ],
    }


@router.post("/catalog/sync")
async def sync_catalog_tournament(
    body: CatalogSyncBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    del user
    configured = ALLOWED_TOURNAMENTS.get(body.league_id)
    if configured is None:
        raise HTTPException(422, "Этот турнир недоступен для создания лиги")

    # Wait for the bulk preload: matches, teams, crests and player rosters are all
    # attempted before the user league is created. A tiny residual roster gap
    # (roughly 10%, max two clubs) is allowed and repaired in the background.
    # Missing crests are always non-blocking and are retried through SStats only.
    try:
        result = await prepare_sstats_competition_tolerant(
            db,
            body.league_id,
            body.year,
            configured["name"],
        )
    except Exception as exc:
        await db.rollback()
        message = _upstream_error_message(exc)
        if len(message) > 500:
            message = message[:497] + "..."
        raise HTTPException(502, f"Турнир пока не готов: {message}. Лига не создана.") from exc

    tournament_id = result.get("tournament_id")
    if not tournament_id or result.get("status") != "ready":
        raise HTTPException(502, "Турнир подготовлен не полностью. Лига не создана.")

    tournament = await db.get(Tournament, int(tournament_id))
    if tournament is None:
        raise HTTPException(502, "Турнир не найден после подготовки")
    tournament.name = configured["name"]
    tournament.country = configured["country"]
    tournament.logo_url = await _sstats_tournament_logo_url(body.league_id)
    await db.commit()

    return {
        "tournament_id": int(tournament.id),
        "provider_id": body.league_id,
        "season": body.year,
        "name": tournament.name,
        "ready": True,
        "sync": result,
    }


@router.get("/{league_id}/theme")
async def get_league_theme(
    league_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return _theme_response(await _theme_league(league_id, user, db))


@router.put("/{league_id}/theme")
async def set_league_theme(
    league_id: int,
    body: LeagueThemeBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    league = await _theme_league(league_id, user, db)
    if league.owner_user_id != user.id and user.role != "superadmin":
        raise HTTPException(403, "Only the league owner can change its interface")
    league.theme_icon = body.icon or None
    league.theme_background = body.background or None
    league.theme_tournament_background = body.tournament_background or None
    await db.commit()
    return _theme_response(league)


from app.test_fixture import router as test_fixture_router
router.include_router(test_fixture_router)
