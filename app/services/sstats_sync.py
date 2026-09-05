from datetime import datetime, timedelta, timezone
import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.competitions.champions_league import classify_ucl_round
from app.models import Match, Team, Tournament
from app.providers.sstats import SStatsProvider
from app.providers.uefa import UEFAProvider

SSTATS_PROVIDER = "sstats"
CHAMPIONS_LEAGUE_ID = 2
UEFA_CHAMPIONS_LEAGUE_ID = 1


def _pick(data: dict, *names: str, default=None):
    for name in names:
        if name in data:
            return data[name]
    return default


def _parse_datetime(value) -> datetime:
    result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result


def _normalize_status(raw_status, kickoff_at: datetime, home_goals, away_goals) -> tuple[str, str | None]:
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
    parts = [f"game_id={game_id}"]
    for key in ("sqlstate", "constraint_name", "detail"):
        value = getattr(orig, key, None)
        if value:
            parts.append(f"{key}={value}")
    return "; ".join(parts)


def _norm(value: str | None) -> str:
    if not value:
        return ""
    text = value.casefold().replace("&", " and ").replace("’", "'")
    text = re.sub(r"[^\w\s']+", " ", text, flags=re.UNICODE)
    tokens = [token for token in text.split() if token not in {"fc", "cf", "afc", "fk", "sc", "ac"}]
    return " ".join(tokens)


def _has_cyrillic(value: str | None) -> bool:
    return bool(re.search(r"[А-Яа-яЁё]", value or ""))


async def _get_or_create_tournament(session: AsyncSession, item: dict) -> Tournament:
    provider_id = int(_pick(item, "leagueId", "LeagueId", default=CHAMPIONS_LEAGUE_ID))
    tournament = await session.scalar(select(Tournament).where(Tournament.provider == SSTATS_PROVIDER, Tournament.provider_id == provider_id))
    name = _pick(item, "leagueName", "LeagueName", default="UEFA Champions League")
    if tournament is None:
        tournament = Tournament(provider=SSTATS_PROVIDER, provider_id=provider_id, name=name)
        session.add(tournament)
        await session.flush()
    tournament.name = name
    tournament.country = _pick(item, "countryName", "CountryName")
    return tournament


async def _get_or_create_team(session: AsyncSession, provider_id: int, name: str) -> Team:
    team = await session.scalar(select(Team).where(Team.provider == SSTATS_PROVIDER, Team.provider_id == provider_id))
    if team is None:
        team = Team(provider=SSTATS_PROVIDER, provider_id=provider_id, name=name)
        session.add(team)
        await session.flush()
    elif not _has_cyrillic(team.name):
        # SStats owns match identity, but once UEFA has supplied a Russian display
        # name we do not overwrite it with SStats' English name on every live sync.
        team.name = name
    return team


async def sync_sstats_champions_league(session: AsyncSession, year: int) -> dict:
    payload = await SStatsProvider().query_games(CHAMPIONS_LEAGUE_ID, year)
    items = payload.get("data") or payload.get("response") or []
    created = updated = skipped = classified_rounds = 0
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
            required = {"game_id": game_id, "home_id": home_id, "away_id": away_id, "home_name": home_name, "away_name": away_name, "date": date_value}
            missing = [key for key, value in required.items() if value is None]
            if missing:
                skipped += 1
                reason = ",".join(missing)
                skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
                continue

            tournament = await _get_or_create_tournament(session, item)
            home_team = await _get_or_create_team(session, int(home_id), str(home_name))
            away_team = await _get_or_create_team(session, int(away_id), str(away_name))
            match = await session.scalar(select(Match).where(Match.provider == SSTATS_PROVIDER, Match.provider_id == int(game_id)))
            is_new = match is None
            kickoff_at = _parse_datetime(date_value)
            season = int(_pick(item, "year", "Year", default=year))
            home_goals = _pick(item, "scoreHome", "ScoreHome", "scoreHomeFT", "ScoreHomeFT")
            away_goals = _pick(item, "scoreAway", "ScoreAway", "scoreAwayFT", "ScoreAwayFT")
            status_short, status_long = _normalize_status(_pick(item, "status", "Status"), kickoff_at, home_goals, away_goals)
            provider_round = _pick(item, "round", "Round", "roundName", "RoundName")
            classified = classify_ucl_round(season, kickoff_at)
            round_name = provider_round or (classified["round_label"] if classified else None)
            if not provider_round and classified:
                classified_rounds += 1

            if is_new:
                match = Match(provider=SSTATS_PROVIDER, provider_id=int(game_id), tournament_id=tournament.id, season=season, kickoff_at=kickoff_at, status_short=status_short, home_team_id=home_team.id, away_team_id=away_team.id)
                session.add(match)
            match.tournament_id = tournament.id
            match.season = season
            match.round_name = round_name
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
            created += int(is_new)
            updated += int(not is_new)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise RuntimeError("SStats database integrity error: " + _integrity_message(exc, current_game_id)) from exc

    result = {"provider": SSTATS_PROVIDER, "league_id": CHAMPIONS_LEAGUE_ID, "year": year, "received": len(items), "created": created, "updated": updated, "classified_rounds": classified_rounds, "skipped": skipped, "skip_reasons": skip_reasons}
    # Metadata enrichment is intentionally best-effort: a temporary UEFA outage must
    # never break the SStats match/live sync.
    try:
        result["team_metadata"] = await sync_sstats_team_metadata(session, limit=None)
    except Exception as exc:
        await session.rollback()
        result["team_metadata"] = {"metadata_source": "uefa", "error": type(exc).__name__}
    return result


async def sync_sstats_team_metadata(session: AsyncSession, limit: int | None = None) -> dict:
    """Enrich SStats teams from UEFA standings using internationalName as the join key.

    SStats remains the match/live provider. UEFA supplies user-facing Russian names,
    official club codes and official crest URLs.
    """
    now = datetime.now(timezone.utc)
    season = now.year + (1 if now.month >= 7 else 0)
    uefa_teams = await UEFAProvider().competition_teams(UEFA_CHAMPIONS_LEAGUE_ID, season)

    by_name: dict[str, object] = {}
    for uefa in uefa_teams:
        for candidate in (uefa.international_name, uefa.name_ru, uefa.name):
            key = _norm(candidate)
            if key:
                by_name[key] = uefa

    query = select(Team).where(Team.provider == SSTATS_PROVIDER).order_by(Team.id)
    if limit is not None:
        query = query.limit(limit)
    teams = (await session.execute(query)).scalars().all()

    updated = unmatched = already_localized = 0
    unmatched_names: list[str] = []
    for team in teams:
        uefa = by_name.get(_norm(team.name))
        if not uefa:
            unmatched += 1
            if len(unmatched_names) < 30:
                unmatched_names.append(team.name)
            continue

        changed = False
        if uefa.name_ru and team.name != uefa.name_ru:
            team.name = uefa.name_ru
            changed = True
        elif _has_cyrillic(team.name):
            already_localized += 1
        if uefa.code and team.code != str(uefa.code)[:20]:
            team.code = str(uefa.code)[:20]
            changed = True
        logo = uefa.logo_medium_url or uefa.logo_url or uefa.logo_big_url or uefa.logo_small_url
        if logo and team.logo_url != logo:
            team.logo_url = logo
            changed = True
        if changed:
            updated += 1

    await session.commit()
    return {
        "provider": SSTATS_PROVIDER,
        "metadata_source": "uefa-standings",
        "competition_id": UEFA_CHAMPIONS_LEAGUE_ID,
        "season_year": season,
        "requested": len(teams),
        "uefa_teams": len(uefa_teams),
        "updated": updated,
        "already_localized": already_localized,
        "unmatched": unmatched,
        "unmatched_names": unmatched_names,
    }
