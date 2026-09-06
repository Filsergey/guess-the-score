import asyncio
from datetime import datetime, timezone

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Match, Player, Team, Tournament
from app.players import sync_sstats_team_players
from app.providers.api_football import APIFootballProvider
from app.providers.sstats import SStatsProvider
from app.services.sstats_sync import SSTATS_PROVIDER, sync_sstats_competition


async def _retry_http(factory, attempts: int = 4):
    last_exc = None
    for attempt in range(attempts):
        try:
            return await factory()
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            status = exc.response.status_code
            if status not in {408, 425, 429} and status < 500:
                raise
            retry_after = exc.response.headers.get("retry-after")
            try:
                delay = max(2.0, float(retry_after)) if retry_after else (4, 10, 20, 35)[attempt]
            except (TypeError, ValueError):
                delay = (4, 10, 20, 35)[attempt]
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_exc = exc
            delay = (2, 5, 10, 20)[attempt]
        if attempt < attempts - 1:
            await asyncio.sleep(delay)
    if last_exc:
        raise last_exc
    raise RuntimeError("SStats request failed")


def _http_label(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        reason = exc.response.reason_phrase or "HTTP error"
        return f"HTTP {status} {reason}"
    return type(exc).__name__


async def _sync_matches_with_cooldown(
    session: AsyncSession,
    league_id: int,
    year: int,
    league_name: str,
):
    """Retry the season sync after cooldowns when SStats is temporarily rate limited."""
    last_exc = None
    for attempt, delay in enumerate((0, 12, 35)):
        if delay:
            await asyncio.sleep(delay)
        try:
            return await sync_sstats_competition(session, league_id, year, league_name)
        except Exception as exc:
            last_exc = exc
            await session.rollback()
            text = str(exc)
            transient = (
                "HTTPStatusError" in text
                or "429" in text
                or "Too Many Requests" in text
                or isinstance(exc, (httpx.TimeoutException, httpx.TransportError))
            )
            if not transient or attempt == 2:
                break
    if last_exc:
        raise last_exc
    raise RuntimeError("Не удалось загрузить матчи")


def _payload_rows(payload: dict) -> list[dict]:
    rows = payload.get("data") or payload.get("response") or []
    if isinstance(rows, dict):
        rows = [rows]
    return [row for row in rows if isinstance(row, dict)]


def _pick(row: dict, *names, default=None):
    for name in names:
        if name in row:
            return row[name]
    return default


def _apply_team_row(team: Team, row: dict) -> None:
    name = _pick(row, "name", "Name")
    if name:
        team.source_name = str(name)
        if not team.uefa_id:
            team.name = str(name)
    code = _pick(row, "code", "Code", "shortName", "ShortName")
    if code:
        team.code = str(code)[:20]
    country = _pick(row, "country", "Country", "countryCode", "CountryCode")
    if isinstance(country, dict):
        country = _pick(country, "code", "Code", "name", "Name")
    if country:
        team.country_code = str(country)[:16]
    logo = _pick(row, "logoUrl", "LogoUrl", "logo", "Logo")
    if isinstance(logo, dict):
        logo = _pick(logo, "url", "Url")
    if logo and str(logo).startswith(("http://", "https://")):
        team.logo_url = str(logo)


def _normalize_team_name(value: str | None) -> str:
    text = str(value or "").lower()
    for token in ("fc", "cf", "afc", "ac", "ssc", "us", "calcio"):
        text = text.replace(token, " ")
    return " ".join(
        text.replace(".", " ").replace("-", " ").replace("_", " ").split()
    )


def _pick_api_football_team(payload: dict, expected_name: str) -> dict:
    rows = payload.get("response") or []
    if not isinstance(rows, list) or not rows:
        return {}
    expected = _normalize_team_name(expected_name)
    for row in rows:
        team = row.get("team") if isinstance(row, dict) else None
        if not isinstance(team, dict):
            continue
        candidate = _normalize_team_name(str(team.get("name") or ""))
        if candidate == expected:
            return team
    if len(rows) == 1 and isinstance(rows[0], dict):
        team = rows[0].get("team")
        return team if isinstance(team, dict) else {}
    return {}


async def _hydrate_missing_logos_from_api_football(
    session: AsyncSession,
    teams: list[Team],
) -> dict:
    missing = [
        team
        for team in teams
        if not team.logo_url or not str(team.logo_url).startswith(("http://", "https://"))
    ]
    if not missing:
        return {"requested": 0, "updated": 0, "configured": True, "failed": []}

    provider = APIFootballProvider()
    if not provider.settings.api_football_key:
        return {
            "requested": len(missing),
            "updated": 0,
            "configured": False,
            "failed": [team.name for team in missing],
        }

    updated = 0
    failed = []
    for team in missing:
        search_name = team.source_name or team.name
        try:
            payload = await provider.search_teams(search_name)
            api_team = _pick_api_football_team(payload, search_name)
            logo = api_team.get("logo") if api_team else None
            if isinstance(logo, str) and logo.startswith(("http://", "https://")):
                team.logo_url = logo
                code = api_team.get("code")
                if code and not team.code:
                    team.code = str(code)[:20]
                updated += 1
            else:
                failed.append(team.name)
        except Exception:
            failed.append(team.name)
    await session.commit()
    return {
        "requested": len(missing),
        "updated": updated,
        "configured": True,
        "failed": failed,
    }


async def _hydrate_team_metadata_bulk(
    session: AsyncSession,
    provider: SStatsProvider,
    teams: list[Team],
) -> None:
    """One Teams/list request instead of one HTTP request per club."""
    payload = await _retry_http(lambda: provider.get_teams(limit=1000), attempts=4)
    rows = _payload_rows(payload)
    by_id = {}
    for row in rows:
        raw_id = _pick(row, "id", "Id")
        try:
            if raw_id is not None:
                by_id[int(raw_id)] = row
        except (TypeError, ValueError):
            continue

    missing = []
    for team in teams:
        row = by_id.get(int(team.provider_id))
        if row:
            _apply_team_row(team, row)
        if not team.logo_url or not str(team.logo_url).startswith(("http://", "https://")):
            missing.append(team)
    await session.commit()

    # Some teams may be absent from the paged catalog. Only those are fetched individually.
    for team in missing:
        try:
            payload = await _retry_http(lambda team=team: provider.get_team(team.provider_id), attempts=3)
            rows = _payload_rows(payload)
            row = rows[0] if rows else (payload.get("data") if isinstance(payload.get("data"), dict) else payload)
            if isinstance(row, dict):
                _apply_team_row(team, row)
        except Exception:
            continue
    await session.commit()


async def prepare_sstats_competition(
    session: AsyncSession,
    league_id: int,
    year: int,
    league_name: str,
):
    """Prepare everything first; only then may the user league be created.

    The anonymous SStats limit is small, so the preparation is deliberately paced
    when SSTATS_API_KEY is not configured. Existing player catalogs are reused.
    """
    sync = await _sync_matches_with_cooldown(session, league_id, year, league_name)
    tournament_id = sync.get("tournament_id")
    if not tournament_id or int(sync.get("received") or 0) <= 0:
        raise RuntimeError("Матчи турнира не загрузились")

    matches = (
        await session.execute(
            select(Match).where(
                Match.provider == SSTATS_PROVIDER,
                Match.tournament_id == int(tournament_id),
                Match.season == int(year),
            )
        )
    ).scalars().all()
    if not matches:
        raise RuntimeError("После синхронизации в базе нет матчей выбранного сезона")

    team_db_ids = {
        tid
        for match in matches
        for tid in (match.home_team_id, match.away_team_id)
        if tid is not None
    }
    teams = (
        await session.execute(select(Team).where(Team.id.in_(team_db_ids)).order_by(Team.name))
    ).scalars().all()
    if len(teams) < 2:
        raise RuntimeError("Не удалось определить команды турнира")

    provider = SStatsProvider()
    try:
        await _hydrate_team_metadata_bulk(session, provider, teams)
    except Exception as exc:
        await session.rollback()
        raise RuntimeError(f"Не удалось загрузить данные команд: {_http_label(exc)}") from exc

    logo_fallback = await _hydrate_missing_logos_from_api_football(session, teams)
    missing_logos = [
        team.name
        for team in teams
        if not team.logo_url or not str(team.logo_url).startswith(("http://", "https://"))
    ]
    if missing_logos:
        preview = ", ".join(missing_logos[:6])
        suffix = "…" if len(missing_logos) > 6 else ""
        extra = (
            " API_FOOTBALL_KEY не настроен."
            if not logo_fallback.get("configured")
            else " API-Football тоже не нашёл логотип."
        )
        raise RuntimeError(f"Не загрузились логотипы команд: {preview}{suffix}.{extra}")

    # With a personal key we can work quickly. Without it SStats documents a 30 req/min
    # per-IP anonymous limit, so keep enough headroom for live updates.
    anonymous = not bool(provider.settings.sstats_api_key)
    pace_seconds = 2.6 if anonymous else 0.12
    player_results = []
    player_errors = []

    for idx, team in enumerate(teams):
        existing = await session.scalar(
            select(func.count(Player.id)).where(
                Player.provider == SSTATS_PROVIDER,
                Player.is_active.is_(True),
                Player.team_provider_id == team.provider_id,
                Player.season == int(year),
            )
        )
        if int(existing or 0) >= 11:
            player_results.append({"team": team.name, "saved": int(existing), "cached": True})
        else:
            try:
                result = await _retry_http(
                    lambda team=team: sync_sstats_team_players(session, team, year),
                    attempts=4,
                )
                player_results.append(result)
                if int(result.get("saved") or 0) <= 0:
                    player_errors.append(f"{team.name}: 0 игроков")
            except Exception as exc:
                await session.rollback()
                player_errors.append(f"{team.name}: {_http_label(exc)}")
        if anonymous and idx < len(teams) - 1:
            await asyncio.sleep(pace_seconds)

    if player_errors:
        preview = ", ".join(player_errors[:5])
        suffix = "…" if len(player_errors) > 5 else ""
        raise RuntimeError(f"Не загрузились игроки: {preview}{suffix}")

    player_counts = {}
    for team in teams:
        count = await session.scalar(
            select(func.count(Player.id)).where(
                Player.provider == SSTATS_PROVIDER,
                Player.is_active.is_(True),
                Player.team_provider_id == team.provider_id,
                Player.season == int(year),
            )
        )
        player_counts[team.provider_id] = int(count or 0)

    empty_teams = [team.name for team in teams if player_counts.get(team.provider_id, 0) <= 0]
    if empty_teams:
        preview = ", ".join(empty_teams[:5])
        suffix = "…" if len(empty_teams) > 5 else ""
        raise RuntimeError(f"Каталог игроков неполный: {preview}{suffix}")

    tournament = await session.get(Tournament, int(tournament_id))
    if tournament:
        tournament.logo_url = f"/api/leagues/tournament-logo/{league_id}"
        await session.commit()

    return {
        **sync,
        "status": "ready",
        "matches_ready": len(matches),
        "teams_ready": len(teams),
        "team_logos_ready": len(teams),
        "players_ready": sum(player_counts.values()),
        "teams_with_players": sum(1 for value in player_counts.values() if value > 0),
        "player_sync": player_results,
        "logo_fallback": logo_fallback,
        "sstats_api_key_configured": not anonymous,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
    }
