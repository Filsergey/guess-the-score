from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.match_status import LIVE_MATCH_STATUSES
from app.models import Match
from app.providers.sstats import SStatsProvider
from app.services.sstats_sync import _normalize_status, _pick


def _rows(payload: dict) -> list[dict]:
    rows = payload.get("data") or payload.get("response") or []
    if isinstance(rows, dict):
        rows = [rows]
    return [SStatsProvider._normalize_game(x) for x in rows if isinstance(x, dict)]


def _int(value):
    try:
        return int(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


async def sync_sstats_live_matches(db: AsyncSession, season: int) -> dict:
    """Refresh only currently live UCL games instead of running the full season sync."""
    provider = SStatsProvider()
    season_info = await provider.resolve_season_uid(2, season)
    kwargs = {"season_uid": season_info["uid"]} if season_info and season_info.get("uid") else {"league_id": 2, "year": season}
    payload = await provider.get_games(**kwargs, live=True, limit=1000)
    rows = _rows(payload)
    ids = [str(_pick(row, "id", "Id")) for row in rows if _pick(row, "id", "Id") is not None]
    matches = (await db.execute(select(Match).where(Match.provider == "sstats", Match.provider_id.in_(ids)))).scalars().all() if ids else []
    by_provider_id = {str(m.provider_id): m for m in matches}
    changed = 0
    for row in rows:
        provider_id = str(_pick(row, "id", "Id"))
        match = by_provider_id.get(provider_id)
        if not match:
            continue
        short, long_name = _normalize_status(_pick(row, "status", "Status"), _pick(row, "statusName", "StatusName"))
        home = _int(_pick(row, "scoreHome", "ScoreHome"))
        away = _int(_pick(row, "scoreAway", "ScoreAway"))
        elapsed = _int(_pick(row, "elapsed", "Elapsed", "minute", "Minute"))
        before = (match.status_short, match.status_long, match.home_goals, match.away_goals, match.elapsed)
        match.status_short = short
        match.status_long = long_name
        if home is not None: match.home_goals = home
        if away is not None: match.away_goals = away
        if elapsed is not None: match.elapsed = elapsed
        after = (match.status_short, match.status_long, match.home_goals, match.away_goals, match.elapsed)
        changed += before != after
    await db.commit()
    return {"season": season, "received": len(rows), "matched": len(matches), "changed": changed, "live_ids": ids, "synced_at": datetime.now(timezone.utc).isoformat()}
