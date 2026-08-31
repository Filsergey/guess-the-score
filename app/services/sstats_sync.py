from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Match, Team, Tournament
from app.providers.sstats import SStatsProvider

SSTATS_PROVIDER = "sstats"
CHAMPIONS_LEAGUE_ID = 2


def _pick(data: dict, *names: str, default=None):
    for name in names:
        if name in data:
            return data[name]
    return default


def _parse_datetime(value) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        result = datetime.fromisoformat(text)
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result


def _normalize_status(raw_status, kickoff_at: datetime, home_goals, away_goals) -> tuple[str, str | None]:
    """Return provider-independent status without guessing SStats numeric codes.

    SStats documents Status as an integer but its public docs do not expose the
    code table in a machine-readable form. Until we add the live adapter, use
    safe facts we do know: future fixtures are NS and past fixtures with a score
    are FT. Preserve the raw provider status in status_long for diagnostics.
    """
    now = datetime.now(timezone.utc)
    raw_text = None if raw_status is None else str(raw_status)
    status_long = f"SStats status {raw_text}" if raw_text is not None else None

    if kickoff_at > now:
        return "NS", status_long

    has_score = home_goals is not None and away_goals is not None
    if has_score and kickoff_at < now - timedelta(hours=2):
        return "FT", status_long

    if kickoff_at <= now <= kickoff_at + timedelta(hours=3):
        return "LIVE" if has_score else "UNKNOWN", status_long

    return "UNKNOWN", status_long


def _integrity_message(exc: IntegrityError, game_id) -> str:
    orig = getattr(exc, "orig", None)
    sqlstate = getattr(orig, "sqlstate", None)
    constraint = getattr(orig, "constraint_name", None)
    detail = getattr(orig, "detail", None)

    parts = [f"game_id={game_id}"]
    if sqlstate:
        parts.append(f"sqlstate={sqlstate}")
    if constraint:
        parts.append(f"constraint={constraint}")
    if detail:
        parts.append(f"detail={detail}")
    if len(parts) == 1 and orig is not None:
        parts.append(str(orig).split("\n")[0][:300])
    return "; ".join(parts)


def _unwrap_data(payload: dict):
    data = payload.get("data") or payload.get("response") or payload
    if isinstance(data, list):
        return data[0] if data else {}
    return data if isinstance(data, dict) else {}


def _find_logo(data: dict) -> str | None:
    direct = _pick(
        data,
        "logo", "Logo",
        "logoUrl", "LogoUrl",
        "image", "Image",
        "imageUrl", "ImageUrl",
        "photo", "Photo",
        "photoUrl", "PhotoUrl",
    )
    if isinstance(direct, str) and direct.startswith(("http://", "https://")):
        return direct

    for key, value in data.items():
        key_lower = str(key).lower()
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            if "logo" in key_lower or "image" in key_lower or "photo" in key_lower:
                return value
        if isinstance(value, dict):
            nested = _find_logo(value)
            if nested:
                return nested
    return None


async def _get_or_create_tournament(session: AsyncSession, item: dict) -> Tournament:
    provider_id = int(_pick(item, "leagueId", "LeagueId", default=CHAMPIONS_LEAGUE_ID))
    tournament = await session.scalar(
        select(Tournament).where(
            Tournament.provider == SSTATS_PROVIDER,
            Tournament.provider_id == provider_id,
        )
    )
    name = _pick(item, "leagueName", "LeagueName", default="UEFA Champions League")
    if tournament is None:
        tournament = Tournament(provider=SSTATS_PROVIDER, provider_id=provider_id, name=name)
        session.add(tournament)
        await session.flush()

    tournament.name = name
    tournament.country = _pick(item, "countryName", "CountryName")
    return tournament


async def _get_or_create_team(session: AsyncSession, provider_id: int, name: str) -> Team:
    team = await session.scalar(
        select(Team).where(
            Team.provider == SSTATS_PROVIDER,
            Team.provider_id == provider_id,
        )
    )
    if team is None:
        team = Team(provider=SSTATS_PROVIDER, provider_id=provider_id, name=name)
        session.add(team)
        await session.flush()
    team.name = name
    return team


async def sync_sstats_champions_league(session: AsyncSession, year: int) -> dict:
    payload = await SStatsProvider().query_games(CHAMPIONS_LEAGUE_ID, year)
    items = payload.get("data") or payload.get("response") or []

    created = 0
    updated = 0
    skipped = 0
    skip_reasons: dict[str, int] = {}
    current_game_id = None

    try:
        for item in items:
            game_id = _pick(item, "id", "Id")
            current_game_id = game_id
            home_id = _pick(item, "homeTeamId", "HomeTeamId")
            away_id = _pick(item, "awayTeamId", "AwayTeamId")
            home_name = _pick(item, "homeTeamName", "HomeTeamName")
            away_name = _pick(item, "awayTeamName", "AwayTeamName")
            date_value = _pick(item, "date", "Date")

            required = {
                "game_id": game_id,
                "home_id": home_id,
                "away_id": away_id,
                "home_name": home_name,
                "away_name": away_name,
                "date": date_value,
            }
            missing = [key for key, value in required.items() if value is None]
            if missing:
                skipped += 1
                reason = ",".join(missing)
                skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
                continue

            tournament = await _get_or_create_tournament(session, item)
            home_team = await _get_or_create_team(session, int(home_id), str(home_name))
            away_team = await _get_or_create_team(session, int(away_id), str(away_name))

            match = await session.scalar(
                select(Match).where(
                    Match.provider == SSTATS_PROVIDER,
                    Match.provider_id == int(game_id),
                )
            )
            is_new = match is None
            kickoff_at = _parse_datetime(date_value)
            raw_status = _pick(item, "status", "Status")
            home_goals = _pick(item, "scoreHome", "ScoreHome", "scoreHomeFT", "ScoreHomeFT")
            away_goals = _pick(item, "scoreAway", "ScoreAway", "scoreAwayFT", "ScoreAwayFT")
            status_short, status_long = _normalize_status(raw_status, kickoff_at, home_goals, away_goals)

            if is_new:
                match = Match(
                    provider=SSTATS_PROVIDER,
                    provider_id=int(game_id),
                    tournament_id=tournament.id,
                    season=int(_pick(item, "year", "Year", default=year)),
                    kickoff_at=kickoff_at,
                    status_short=status_short,
                    home_team_id=home_team.id,
                    away_team_id=away_team.id,
                )
                session.add(match)

            match.tournament_id = tournament.id
            match.season = int(_pick(item, "year", "Year", default=year))
            match.round_name = _pick(item, "round", "Round", "roundName", "RoundName")
            match.kickoff_at = kickoff_at
            match.status_short = status_short
            match.status_long = status_long
            match.elapsed = None
            match.home_team_id = home_team.id
            match.away_team_id = away_team.id
            match.home_goals = home_goals
            match.away_goals = away_goals
            match.updated_at = datetime.now(timezone.utc)

            await session.flush()

            if is_new:
                created += 1
            else:
                updated += 1

        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise RuntimeError(
            "SStats database integrity error: " + _integrity_message(exc, current_game_id)
        ) from exc

    return {
        "provider": SSTATS_PROVIDER,
        "league_id": CHAMPIONS_LEAGUE_ID,
        "year": year,
        "received": len(items),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "skip_reasons": skip_reasons,
    }


async def sync_sstats_team_metadata(session: AsyncSession, limit: int = 20) -> dict:
    """Enrich SStats teams in small batches to stay below anonymous API limits."""
    teams = (
        await session.execute(
            select(Team)
            .where(Team.provider == SSTATS_PROVIDER, Team.logo_url.is_(None))
            .order_by(Team.id)
            .limit(limit)
        )
    ).scalars().all()

    provider = SStatsProvider()
    updated = 0
    without_logo = 0
    failed = 0

    for team in teams:
        try:
            payload = await provider.get_team(team.provider_id)
            data = _unwrap_data(payload)
            name = _pick(data, "name", "Name", "teamName", "TeamName")
            code = _pick(data, "code", "Code", "shortName", "ShortName")
            logo = _find_logo(data)

            if name:
                team.name = str(name)
            if code:
                team.code = str(code)[:20]
            if logo:
                team.logo_url = logo
                updated += 1
            else:
                without_logo += 1
        except Exception:
            failed += 1

    await session.commit()
    return {
        "provider": SSTATS_PROVIDER,
        "requested": len(teams),
        "logos_updated": updated,
        "without_logo": without_logo,
        "failed": failed,
        "remaining_without_logo": await session.scalar(
            select(__import__("sqlalchemy").func.count(Team.id)).where(
                Team.provider == SSTATS_PROVIDER,
                Team.logo_url.is_(None),
            )
        ),
    }
