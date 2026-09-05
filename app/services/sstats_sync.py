from datetime import datetime, timezone
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

SSTATS_STATUSES = {
    1: ("TBD", "Date/time to be defined"),
    2: ("NS", "Not started"),
    3: ("1H", "First half"),
    4: ("HT", "Half-time"),
    5: ("2H", "Second half"),
    6: ("ET", "Extra time"),
    7: ("PEN_LIVE", "Penalties in progress"),
    8: ("FT", "Full-time"),
    9: ("AET", "After extra time"),
    10: ("PEN", "Finished after penalties"),
    11: ("ET_BREAK", "Extra-time break"),
    12: ("SUSP", "Suspended"),
    13: ("ABD", "Abandoned"),
    14: ("PST", "Postponed"),
    15: ("CANC", "Cancelled"),
    17: ("AWD", "Technical loss"),
    18: ("WO", "Walkover"),
    19: ("LIVE", "In progress"),
}


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


def _normalize_status(raw_status, raw_status_name=None) -> tuple[str, str | None]:
    """Map the documented SStats status code instead of guessing from kickoff time/score."""
    try:
        code = int(raw_status) if raw_status is not None else None
    except (TypeError, ValueError):
        code = None
    mapped = SSTATS_STATUSES.get(code)
    provider_name = str(raw_status_name).strip() if raw_status_name not in (None, "") else None
    if mapped:
        short, fallback_name = mapped
        return short, provider_name or fallback_name
    raw_text = None if raw_status is None else str(raw_status)
    return "UNKNOWN", provider_name or (f"SStats status {raw_text}" if raw_text is not None else None)


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
    text = (
        text.replace("ø", "o").replace("ö", "o").replace("ó", "o").replace("ò", "o").replace("ô", "o")
        .replace("ü", "u").replace("ú", "u").replace("ä", "a").replace("á", "a").replace("à", "a")
        .replace("é", "e").replace("è", "e").replace("í", "i").replace("ñ", "n").replace("ç", "c")
    )
    text = re.sub(r"[^\w\s']+", " ", text, flags=re.UNICODE)
    tokens = [token for token in text.split() if token not in {"fc", "cf", "afc", "fk", "sc", "ac", "fa"}]
    normalized = " ".join(tokens)
    aliases = {
        "atletico madrid": "atleti",
        "atletico de madrid": "atleti",
        "club atletico de madrid": "atleti",
        "lask linz": "lask",
        "sabah masazir": "sabah",
    }
    return aliases.get(normalized, normalized)


def _norm_code(value: str | None) -> str:
    code = re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
    return {"LAS": "LASK"}.get(code, code)


def _has_cyrillic(value: str | None) -> bool:
    return bool(re.search(r"[А-Яа-яЁё]", value or ""))


def _items(payload: dict) -> list[dict]:
    rows = payload.get("data") or payload.get("response") or []
    return rows if isinstance(rows, list) else []


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
        team = Team(provider=SSTATS_PROVIDER, provider_id=provider_id, name=name, source_name=name)
        session.add(team)
        await session.flush()
    else:
        team.source_name = name
        if not team.uefa_id and not _has_cyrillic(team.name):
            team.name = name
    return team


async def sync_sstats_champions_league(session: AsyncSession, year: int) -> dict:
    provider = SStatsProvider()
    payload, season_ref = await provider.competition_games(CHAMPIONS_LEAGUE_ID, year)
    items = _items(payload)
    created = updated = skipped = classified_rounds = 0
    skip_reasons: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    current_game_id = None
    try:
        for item in items:
            game_id = _pick(item, "id", "Id"); current_game_id = game_id
            home_id = _pick(item, "homeTeamId", "HomeTeamId"); away_id = _pick(item, "awayTeamId", "AwayTeamId")
            home_name = _pick(item, "homeTeamName", "HomeTeamName"); away_name = _pick(item, "awayTeamName", "AwayTeamName")
            date_value = _pick(item, "date", "Date")
            required = {"game_id":game_id,"home_id":home_id,"away_id":away_id,"home_name":home_name,"away_name":away_name,"date":date_value}
            missing = [k for k,v in required.items() if v is None]
            if missing:
                skipped += 1; reason=",".join(missing); skip_reasons[reason]=skip_reasons.get(reason,0)+1; continue
            tournament = await _get_or_create_tournament(session,item)
            home_team = await _get_or_create_team(session,int(home_id),str(home_name)); away_team = await _get_or_create_team(session,int(away_id),str(away_name))
            match = await session.scalar(select(Match).where(Match.provider==SSTATS_PROVIDER,Match.provider_id==int(game_id)))
            is_new = match is None; kickoff_at=_parse_datetime(date_value); season=int(_pick(item,"year","Year",default=year))
            home_goals=_pick(item,"scoreHome","ScoreHome","scoreHomeFT","ScoreHomeFT"); away_goals=_pick(item,"scoreAway","ScoreAway","scoreAwayFT","ScoreAwayFT")
            raw_status=_pick(item,"status","Status"); raw_status_name=_pick(item,"statusName","StatusName")
            status_short,status_long=_normalize_status(raw_status,raw_status_name); status_counts[status_short]=status_counts.get(status_short,0)+1
            provider_round=_pick(item,"round","Round","roundName","RoundName"); classified=classify_ucl_round(season,kickoff_at); round_name=provider_round or (classified["round_label"] if classified else None)
            if not provider_round and classified: classified_rounds += 1
            if is_new:
                match=Match(provider=SSTATS_PROVIDER,provider_id=int(game_id),tournament_id=tournament.id,season=season,kickoff_at=kickoff_at,status_short=status_short,home_team_id=home_team.id,away_team_id=away_team.id); session.add(match)
            match.tournament_id=tournament.id; match.season=season; match.round_name=round_name; match.kickoff_at=kickoff_at; match.status_short=status_short; match.status_long=status_long; match.elapsed=None; match.home_team_id=home_team.id; match.away_team_id=away_team.id; match.home_goals=home_goals; match.away_goals=away_goals; match.updated_at=datetime.now(timezone.utc)
            await session.flush(); created += int(is_new); updated += int(not is_new)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback(); raise RuntimeError("SStats database integrity error: "+_integrity_message(exc,current_game_id)) from exc

    result={"provider":SSTATS_PROVIDER,"league_id":CHAMPIONS_LEAGUE_ID,"year":year,"season_ref":{k:v for k,v in season_ref.items() if k!='raw'},"received":len(items),"created":created,"updated":updated,"classified_rounds":classified_rounds,"skipped":skipped,"skip_reasons":skip_reasons,"status_counts":status_counts}
    try: result["team_metadata"] = await sync_sstats_team_metadata(session)
    except Exception as exc:
        await session.rollback(); result["team_metadata"]={"error":type(exc).__name__}
    return result


async def sync_sstats_team_metadata(session: AsyncSession, limit: int | None = None) -> dict:
    """SStats owns team IDs; UEFA enriches only the 36 current UCL main-stage teams."""
    provider = SStatsProvider()
    sstats_rows = _items(await provider.get_teams(limit=1000))
    sstats_by_id = {}
    for row in sstats_rows:
        raw_id = _pick(row,"id","Id")
        if raw_id is not None:
            sstats_by_id[int(raw_id)] = row

    query=select(Team).where(Team.provider==SSTATS_PROVIDER).order_by(Team.id)
    if limit is not None: query=query.limit(limit)
    teams=(await session.execute(query)).scalars().all()

    for team in teams:
        src=sstats_by_id.get(team.provider_id)
        if not src: continue
        source_name=str(_pick(src,"name","Name",default=team.source_name or team.name))
        team.source_name=source_name
        country=_pick(src,"country","Country")
        if isinstance(country,dict): team.country_code=str(_pick(country,"code","Code",default="") or "")[:16] or team.country_code
        sstats_logo=_pick(src,"logoUrl","LogoUrl")
        if sstats_logo and not team.logo_url: team.logo_url=str(sstats_logo)

    now=datetime.now(timezone.utc); season=now.year+(1 if now.month>=7 else 0)
    sstats_season=season-1
    main_stage_matches=(await session.execute(select(Match).where(Match.provider==SSTATS_PROVIDER,Match.season==sstats_season))).scalars().all()
    main_stage_team_ids={
        team_id
        for match in main_stage_matches
        if classify_ucl_round(sstats_season,match.kickoff_at) is not None
        for team_id in (match.home_team_id,match.away_team_id)
        if team_id is not None
    }

    uefa_teams=await UEFAProvider().competition_teams(UEFA_CHAMPIONS_LEAGUE_ID,season)
    by_name={}; code_candidates={}
    for uefa in uefa_teams:
        candidates=[uefa.international_name,uefa.name_ru,uefa.name]
        candidates.extend(getattr(uefa,"aliases",()) or ())
        for candidate in candidates:
            key=_norm(candidate)
            if key: by_name[key]=uefa
        code=_norm_code(uefa.code)
        if code: code_candidates.setdefault(code,[]).append(uefa)
    by_code={code:rows[0] for code,rows in code_candidates.items() if len(rows)==1}

    updated=0; unmatched_names=[]; matched_uefa_ids=set(); main_stage_unmatched=[]
    current_uefa_ids={u.id for u in uefa_teams}
    for team in teams:
        if team.id not in main_stage_team_ids:
            if team.uefa_id in current_uefa_ids:
                team.uefa_id=None
            if len(unmatched_names)<40:
                unmatched_names.append(team.source_name or team.name)
            continue
        uefa=None
        for candidate in (team.source_name,team.name):
            key=_norm(candidate)
            if key and key in by_name:
                uefa=by_name[key]
                break
        if not uefa:
            code=_norm_code(team.code)
            if code: uefa=by_code.get(code)
        if not uefa:
            main_stage_unmatched.append(team.source_name or team.name)
            continue
        matched_uefa_ids.add(uefa.id)
        team.uefa_id=uefa.id
        if uefa.name_ru: team.name=uefa.name_ru
        if uefa.code: team.code=str(uefa.code)[:20]
        if uefa.country_code: team.country_code=str(uefa.country_code)[:16]
        logo=uefa.logo_medium_url or uefa.logo_url or uefa.logo_big_url or uefa.logo_small_url
        if logo: team.logo_url=logo
        updated+=1
    await session.commit()
    non_main_stage=sum(1 for team in teams if team.id not in main_stage_team_ids)
    return {
        "provider":"sstats",
        "catalog_source":"sstats:/Teams/list",
        "metadata_source":"uefa-standings",
        "season_year":season,
        "teams_in_db":len(teams),
        "sstats_catalog":len(sstats_rows),
        "uefa_catalog":len(uefa_teams),
        "main_stage_teams":sum(1 for team in teams if team.id in main_stage_team_ids),
        "updated":updated,
        "uefa_matched":len(matched_uefa_ids),
        "uefa_unmatched":len(uefa_teams)-len(matched_uefa_ids),
        "main_stage_unmatched":main_stage_unmatched,
        "unmatched_non_uefa":non_main_stage,
        "unmatched_names":unmatched_names,
    }