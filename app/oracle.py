import asyncio
import hashlib
import json
import logging
import math
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from openai import AsyncOpenAI
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import Match, OraclePrediction, Team, Tournament
from app.providers.sstats import SStatsProvider

router = APIRouter(prefix="/api/oracle", tags=["oracle"])
settings = get_settings()
logger = logging.getLogger(__name__)
CACHE_SCHEMA_VERSION = 5
MIN_READABLE_CACHE_VERSION = 4
ANALYSIS_LOCK = asyncio.Lock()
_MATCH_LOCKS: dict[int, asyncio.Lock] = {}

ANALYSIS_INSTRUCTIONS = """Ты футбольный аналитик приложения «Угадай счёт».
Интернет и web_search НЕ используются. Используй только структурированные данные сервера.
Сервер передаёт данные матча, последние матчи команд, H2H, форму, xG/Glicko, коэффициенты и турнирное положение.
Самостоятельно построй прогноз результата матча. Не выдумывай отсутствующие факты. Если данных мало — снижай confidence/data_quality.

Для mode=initial верни полный прогноз.
Для mode=delta передаются previous_forecast и ТОЛЬКО изменившиеся поля context. Не пересчитывай матч с нуля и не меняй прогноз без существенной причины. Если изменения не влияют на прогноз, верни {"match_id":123,"unchanged":true}. Если влияют — можно вернуть только изменившиеся поля прогноза, остальные будут сохранены из previous_forecast.

Формат ответа — ТОЛЬКО JSON без markdown:
{"matches":[{"match_id":123,"home_score":1,"away_score":1,"confidence":60,"data_quality":"high|medium|low","probabilities":{"home":30,"draw":35,"away":35},"reasoning":"2-4 конкретных предложения по-русски","key_factors":["3-5 факторов"],"failure_risks":["2-4 риска"]}]}
Вероятности, если возвращаются, должны суммироваться до 100. Счёт — целые числа 0..20."""


def _num(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _prob(value):
    x = _num(value)
    if x is None:
        return None
    if x > 1:
        x /= 100
    return max(0.0, min(1.0, x))


def _first(payload):
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data") or payload.get("response") or []
    return data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else {})


def _v(data, name):
    return data.get(name[:1].lower() + name[1:], data.get(name))


def _signals(details, glicko):
    return {
        "glicko_xg": {
            "home": _num(_v(details, "GlickoXgHome")) or _num(_v(glicko, "XgHome")),
            "away": _num(_v(details, "GlickoXgAway")) or _num(_v(glicko, "XgAway")),
        },
        "odds_xg": {
            "home": _num(_v(details, "OddsXgHome")),
            "away": _num(_v(details, "OddsXgAway")),
        },
        "glicko_win_probability": {
            "home": _prob(_v(details, "GlickoWinProbHome")) or _prob(_v(glicko, "WinProbHome")),
            "away": _prob(_v(details, "GlickoWinProbAway")) or _prob(_v(glicko, "WinProbAway")),
        },
        "odds": {
            "home": _num(_v(details, "Winner1")),
            "draw": _num(_v(details, "WinnerX")),
            "away": _num(_v(details, "Winner2")),
        },
    }


async def _load_provider_signals(match):
    details, glicko, errors = {}, {}, []
    if match.provider == "sstats":
        provider = SStatsProvider()
        try:
            details = _first(await provider.query_game_details(match.provider_id))
        except Exception as exc:
            errors.append(f"details:{type(exc).__name__}")
        try:
            glicko = _first(await provider.get_glicko(match.provider_id))
        except Exception as exc:
            errors.append(f"glicko:{type(exc).__name__}")
    return _signals(details, glicko), errors


async def _recent_models(team_id, before, db, limit=5):
    return (
        await db.execute(
            select(Match)
            .where(
                Match.kickoff_at < before,
                Match.home_goals.is_not(None),
                Match.away_goals.is_not(None),
                or_(Match.home_team_id == team_id, Match.away_team_id == team_id),
            )
            .order_by(Match.kickoff_at.desc())
            .limit(limit)
        )
    ).scalars().all()


async def _recent_form(team_id, before, db, limit=6):
    rows = await _recent_models(team_id, before, db, limit)
    if not rows:
        return {"count": 0, "gf": None, "ga": None, "ppg": None}
    gf = ga = pts = 0
    for match in rows:
        own, opp = (
            (match.home_goals, match.away_goals)
            if match.home_team_id == team_id
            else (match.away_goals, match.home_goals)
        )
        gf += own
        ga += opp
        pts += 3 if own > opp else (1 if own == opp else 0)
    n = len(rows)
    return {"count": n, "gf": round(gf / n, 2), "ga": round(ga / n, 2), "ppg": round(pts / n, 2)}


async def _name_maps(db, matches):
    team_ids = {m.home_team_id for m in matches} | {m.away_team_id for m in matches}
    tournament_ids = {m.tournament_id for m in matches if m.tournament_id is not None}
    teams = (await db.execute(select(Team).where(Team.id.in_(team_ids)))).scalars().all() if team_ids else []
    tournaments = (
        (await db.execute(select(Tournament).where(Tournament.id.in_(tournament_ids)))).scalars().all()
        if tournament_ids
        else []
    )
    return {x.id: x.name for x in teams}, {x.id: x.name for x in tournaments}


async def _recent_rows(team_id, before, db, limit=5):
    models = await _recent_models(team_id, before, db, limit)
    team_names, tournament_names = await _name_maps(db, models)
    rows = []
    for match in models:
        own_home = match.home_team_id == team_id
        own = match.home_goals if own_home else match.away_goals
        opp = match.away_goals if own_home else match.home_goals
        rows.append({
            "date": match.kickoff_at.date().isoformat(),
            "home": team_names.get(match.home_team_id, "Хозяева"),
            "away": team_names.get(match.away_team_id, "Гости"),
            "score": f"{match.home_goals}:{match.away_goals}",
            "competition": tournament_names.get(match.tournament_id) or match.round_name or "",
            "result": "W" if own > opp else ("D" if own == opp else "L"),
        })
    return rows


async def _h2h_rows(home_id, away_id, before, db, limit=5):
    rows = (
        await db.execute(
            select(Match)
            .where(
                Match.kickoff_at < before,
                Match.home_goals.is_not(None),
                Match.away_goals.is_not(None),
                or_(
                    and_(Match.home_team_id == home_id, Match.away_team_id == away_id),
                    and_(Match.home_team_id == away_id, Match.away_team_id == home_id),
                ),
            )
            .order_by(Match.kickoff_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    team_names, tournament_names = await _name_maps(db, rows)
    return [{
        "date": match.kickoff_at.date().isoformat(),
        "home": team_names.get(match.home_team_id, "Хозяева"),
        "away": team_names.get(match.away_team_id, "Гости"),
        "score": f"{match.home_goals}:{match.away_goals}",
        "competition": tournament_names.get(match.tournament_id) or match.round_name or "",
    } for match in rows]


async def _standings_pair(match, db):
    rows = (
        await db.execute(
            select(Match).where(
                Match.tournament_id == match.tournament_id,
                Match.season == match.season,
                Match.kickoff_at < match.kickoff_at,
                Match.home_goals.is_not(None),
                Match.away_goals.is_not(None),
            )
        )
    ).scalars().all()
    stats = {}
    for row in rows:
        for team_id, gf, ga in (
            (row.home_team_id, row.home_goals, row.away_goals),
            (row.away_team_id, row.away_goals, row.home_goals),
        ):
            item = stats.setdefault(team_id, {"played": 0, "points": 0, "gf": 0, "ga": 0})
            item["played"] += 1
            item["gf"] += gf
            item["ga"] += ga
            item["points"] += 3 if gf > ga else (1 if gf == ga else 0)
    ordered = sorted(
        stats.items(),
        key=lambda x: (x[1]["points"], x[1]["gf"] - x[1]["ga"], x[1]["gf"]),
        reverse=True,
    )
    places = {team_id: index + 1 for index, (team_id, _) in enumerate(ordered)}

    def one(team_id):
        item = stats.get(team_id, {"played": 0, "points": 0, "gf": 0, "ga": 0})
        return {**item, "place": places.get(team_id)}

    return {"home": one(match.home_team_id), "away": one(match.away_team_id)}


def _json_text(text):
    value = (text or "").strip()
    if "{" in value and "}" in value:
        value = value[value.find("{") : value.rfind("}") + 1]
    return json.loads(value)


def _clean_text(value):
    if value is None:
        return None
    text = str(value)
    text = re.sub(r"\[[^\]]+\]\s*\(https?://[^)]+\)", "", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def _strings(value, limit=8):
    if not isinstance(value, list):
        return []
    result = []
    for item in value[:limit]:
        text = _clean_text(item)
        if text:
            result.append(text)
    return result


def _canonical_hash(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _payload_from_row(row):
    if row is None:
        return None
    try:
        return json.loads(row.payload_json)
    except Exception:
        return None


def _is_ai_payload(payload):
    return bool(isinstance(payload, dict) and payload.get("ai_analyzed_at") and payload.get("source") == "openai-analysis")


async def _match_context(match, db):
    home = await db.get(Team, match.home_team_id)
    away = await db.get(Team, match.away_team_id)
    signals, errors = await _load_provider_signals(match)
    home_form = await _recent_form(match.home_team_id, match.kickoff_at, db)
    away_form = await _recent_form(match.away_team_id, match.kickoff_at, db)
    recent = {
        "home": await _recent_rows(match.home_team_id, match.kickoff_at, db),
        "away": await _recent_rows(match.away_team_id, match.kickoff_at, db),
    }
    h2h = await _h2h_rows(match.home_team_id, match.away_team_id, match.kickoff_at, db)
    standings = await _standings_pair(match, db)
    snapshot = {
        "match": {
            "match_id": match.id,
            "home": home.name if home else "Хозяева",
            "away": away.name if away else "Гости",
            "kickoff_at": match.kickoff_at.isoformat(),
            "season": match.season,
            "round": match.round_name,
        },
        "signals": signals,
        "form": {"home": home_form, "away": away_form},
        "recent_matches": recent,
        "head_to_head_matches": h2h,
        "standings": standings,
    }
    return {
        "match": match,
        "home": home,
        "away": away,
        "signals": signals,
        "home_form": home_form,
        "away_form": away_form,
        "recent_matches": recent,
        "head_to_head_matches": h2h,
        "standings": standings,
        "errors": errors,
        "snapshot": snapshot,
        "context_hash": _canonical_hash(snapshot),
    }


def _form_text(form):
    if not form or not form.get("count"):
        return "нет достаточных данных"
    return f"{form['count']} матч.: {form['gf']:.2f} забито, {form['ga']:.2f} пропущено, {form['ppg']:.2f} очка/игру"


def _h2h_summary(rows):
    if not rows:
        return "В нашей базе нет завершённых очных встреч до этого матча."
    last = rows[0]
    return f"В базе найдено {len(rows)} последних очных встреч. Последняя: {last['date']} — {last['home']} — {last['away']} {last['score']}."


def _display_xg(ctx):
    signals = ctx["signals"]
    for key in ("glicko_xg", "odds_xg"):
        home = signals[key].get("home")
        away = signals[key].get("away")
        if home is not None and away is not None:
            return {"home": round(float(home), 2), "away": round(float(away), 2)}
    return None


def _normalize_ai(row, fallback=None):
    fallback = fallback if isinstance(fallback, dict) else {}
    if row.get("unchanged") and fallback:
        base = dict(fallback)
        base["ai_unchanged"] = True
        return base

    raw_home = _num(row.get("home_score"))
    raw_away = _num(row.get("away_score"))
    if raw_home is None:
        raw_home = _num(fallback.get("home_score"))
    if raw_away is None:
        raw_away = _num(fallback.get("away_score"))
    if raw_home is None or raw_away is None:
        return None
    home_score = max(0, min(20, int(raw_home)))
    away_score = max(0, min(20, int(raw_away)))

    probabilities = fallback.get("probabilities") if isinstance(fallback.get("probabilities"), dict) else None
    if isinstance(row.get("probabilities"), dict):
        probs = row["probabilities"]
        ph, pd, pa = _num(probs.get("home")), _num(probs.get("draw")), _num(probs.get("away"))
        if all(x is not None and x >= 0 for x in (ph, pd, pa)) and ph + pd + pa > 0:
            total = ph + pd + pa
            probabilities = {
                "home": round(ph * 100 / total, 1),
                "draw": round(pd * 100 / total, 1),
                "away": round(pa * 100 / total, 1),
            }

    raw_conf = _num(row.get("confidence"))
    if raw_conf is None:
        raw_conf = _num(fallback.get("confidence"))
    if raw_conf is None and probabilities:
        raw_conf = max(probabilities.values())
    confidence = max(0, min(100, int(raw_conf if raw_conf is not None else 50)))

    quality = str(row.get("data_quality") or fallback.get("data_quality") or "medium").lower()
    if quality not in {"high", "medium", "low"}:
        quality = "medium"

    reasoning = _clean_text(row.get("reasoning")) or fallback.get("reasoning") or "Прогноз построен OpenAI по данным SStats и нашей базы."
    key_factors = _strings(row.get("key_factors"), 6) or list(fallback.get("key_factors") or [])
    failure_risks = _strings(row.get("failure_risks"), 5) or list(fallback.get("failure_risks") or [])
    return {
        "home_score": home_score,
        "away_score": away_score,
        "outcome": "home" if home_score > away_score else ("away" if away_score > home_score else "draw"),
        "confidence": confidence,
        "data_quality": quality,
        "probabilities": probabilities,
        "reasoning": reasoning,
        "key_factors": key_factors,
        "failure_risks": failure_risks,
    }


def _diff_context(old, new):
    if old == new:
        return None
    if isinstance(old, dict) and isinstance(new, dict):
        result = {}
        for key in sorted(set(old) | set(new)):
            if key not in old:
                result[key] = {"after": new[key]}
            elif key not in new:
                result[key] = {"removed": True}
            else:
                diff = _diff_context(old[key], new[key])
                if diff is not None:
                    result[key] = diff
        return result or None
    if isinstance(old, list) and isinstance(new, list):
        return {"after": new}
    return {"before": old, "after": new}


def _previous_forecast(payload):
    if not isinstance(payload, dict):
        return None
    return {
        key: payload.get(key)
        for key in (
            "home_score",
            "away_score",
            "confidence",
            "data_quality",
            "probabilities",
            "reasoning",
            "key_factors",
            "failure_risks",
        )
    }


async def _ai_analyze_batch(items):
    if not settings.openai_oracle_enabled or not settings.openai_api_key or not items:
        return {}
    dynamic = []
    for item in items:
        row = {"match_id": item["ctx"]["match"].id, "mode": item["mode"]}
        if item["mode"] == "initial":
            row["context"] = item["ctx"]["snapshot"]
        else:
            row["previous_forecast"] = _previous_forecast(item["previous"])
            row["changes"] = item["changes"]
        dynamic.append(row)
    prompt = ANALYSIS_INSTRUCTIONS + "\nДанные для анализа:\n" + json.dumps(dynamic, ensure_ascii=False, default=str)
    try:
        async with ANALYSIS_LOCK:
            response = await AsyncOpenAI(api_key=settings.openai_api_key).responses.create(
                model=settings.openai_oracle_model,
                input=prompt,
                max_output_tokens=max(650, 380 * len(items)),
            )
        raw = _json_text(response.output_text)
        rows = raw.get("matches") if isinstance(raw, dict) else None
        if not isinstance(rows, list):
            return {}
        valid = {item["ctx"]["match"].id: item for item in items}
        result = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            match_id = int(_num(row.get("match_id")) or 0)
            item = valid.get(match_id)
            if not item:
                continue
            fallback = _previous_forecast(item["previous"]) if item["mode"] == "delta" else None
            normalized = _normalize_ai(row, fallback)
            if normalized:
                result[match_id] = normalized
        if getattr(response, "usage", None):
            logger.info("Oracle analysis OpenAI usage: %s", response.usage)
        return result
    except Exception:
        logger.exception("Oracle analysis failed")
        return {}


def _compose_payload(ctx, ai, mode):
    now = datetime.now(timezone.utc).isoformat()
    result = dict(ai)
    result.update({
        "schema_version": CACHE_SCHEMA_VERSION,
        "match_id": ctx["match"].id,
        "source": "openai-analysis",
        "details_errors": ctx["errors"],
        "context_hash": ctx["context_hash"],
        "analysis_context_hash": ctx["context_hash"],
        "context_snapshot": ctx["snapshot"],
        "context_checked_at": now,
        "ai_analyzed_at": now,
        "ai_mode": mode,
        "xg": _display_xg(ctx),
        "form": {"home": _form_text(ctx["home_form"]), "away": _form_text(ctx["away_form"])},
        "recent_matches": ctx["recent_matches"],
        "head_to_head": _h2h_summary(ctx["head_to_head_matches"]),
        "head_to_head_matches": ctx["head_to_head_matches"],
        "injuries": [],
    })
    return result


async def _save_cache(db, match_id, data, bump_generated=True):
    match = await db.get(Match, match_id)
    now = datetime.now(timezone.utc)
    if match is None or now >= match.kickoff_at:
        return False
    row = (await db.execute(select(OraclePrediction).where(OraclePrediction.match_id == match_id))).scalar_one_or_none()
    if row is not None and row.locked_at is not None and now >= row.locked_at:
        return False
    data["schema_version"] = CACHE_SCHEMA_VERSION
    data["locked_at"] = match.kickoff_at.isoformat()
    payload = json.dumps(data, ensure_ascii=False, default=str)
    if row is None:
        row = OraclePrediction(
            match_id=match_id,
            payload_json=payload,
            source="openai-analysis",
            generated_at=now,
            locked_at=match.kickoff_at,
            updated_at=now,
        )
        db.add(row)
    else:
        row.payload_json = payload
        row.source = "openai-analysis"
        if bump_generated:
            row.generated_at = now
        row.locked_at = match.kickoff_at
        row.updated_at = now
    return True


async def _get_cache(db, match_id, require_ai=True):
    row = (await db.execute(select(OraclePrediction).where(OraclePrediction.match_id == match_id))).scalar_one_or_none()
    if not row:
        return None
    data = _payload_from_row(row)
    if not data or int(data.get("schema_version") or 0) < MIN_READABLE_CACHE_VERSION:
        return None
    if require_ai and not _is_ai_payload(data):
        return None
    data.pop("sources", None)
    data["cached"] = True
    data["generated_at"] = row.generated_at
    data["locked_at"] = row.locked_at
    return data


def _needs_refresh(match, cache_row, now):
    """Compatibility helper for manual admin generation; no scheduler calls it anymore."""
    if match.kickoff_at <= now:
        return False
    payload = _payload_from_row(cache_row)
    if not _is_ai_payload(payload):
        return True
    return payload.get("analysis_context_hash") != payload.get("context_hash")


async def _refresh_one_context(db, match, force=False):
    row = (await db.execute(select(OraclePrediction).where(OraclePrediction.match_id == match.id))).scalar_one_or_none()
    previous = _payload_from_row(row)
    if not _is_ai_payload(previous):
        previous = None
    ctx = await _match_context(match, db)
    if previous:
        analysis_hash = previous.get("analysis_context_hash") or previous.get("context_hash")
        changed = analysis_hash != ctx["context_hash"]
        if not force and not changed:
            return {"match_id": match.id, "status": "cache-unchanged", "ai": False, "previous": previous, "ctx": ctx}
        changes = _diff_context(previous.get("context_snapshot") or {}, ctx["snapshot"]) or {}
        return {
            "match_id": match.id,
            "status": "needs-ai",
            "ai": True,
            "ctx": ctx,
            "previous": previous,
            "changes": changes,
            "mode": "delta",
        }
    return {
        "match_id": match.id,
        "status": "needs-ai",
        "ai": True,
        "ctx": ctx,
        "previous": None,
        "changes": None,
        "mode": "initial",
    }


async def generate_or_refresh_matches(db, matches, force=False, refresh_news=False):
    """Generate initial/delta OpenAI predictions. No local forecast and no web search."""
    if not matches:
        return {"requested": 0, "generated": 0, "unchanged": 0, "failed": 0, "ai_requested": 0}
    work, unchanged = [], 0
    for match in matches:
        if match.kickoff_at <= datetime.now(timezone.utc):
            continue
        item = await _refresh_one_context(db, match, force=force)
        if item["status"] == "cache-unchanged":
            unchanged += 1
        else:
            work.append(item)
    ai_result = await _ai_analyze_batch(work)
    generated = failed = 0
    for item in work:
        ai = ai_result.get(item["match_id"])
        if ai is None:
            failed += 1
            continue
        payload = _compose_payload(item["ctx"], ai, item["mode"])
        if await _save_cache(db, item["match_id"], payload, bump_generated=True):
            generated += 1
    await db.commit()
    return {
        "requested": len(matches),
        "generated": generated,
        "unchanged": unchanged,
        "failed": failed,
        "ai_requested": len(work),
        "ai_modes": {
            "initial": sum(1 for x in work if x["mode"] == "initial"),
            "delta": sum(1 for x in work if x["mode"] == "delta"),
        },
    }


def _match_lock(match_id):
    lock = _MATCH_LOCKS.get(match_id)
    if lock is None:
        lock = asyncio.Lock()
        _MATCH_LOCKS[match_id] = lock
    return lock


@router.post("/admin/generate-batch")
async def generate_batch(
    batch_size: int = Query(default=5, ge=1, le=10),
    hours_ahead: int = Query(default=120, ge=3, le=336),
    season: int | None = Query(default=None, ge=2020, le=2100),
    force: bool = Query(default=False),
    x_admin_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    if not settings.admin_sync_token:
        raise HTTPException(503, "ADMIN_SYNC_TOKEN is not configured")
    if x_admin_token != settings.admin_sync_token:
        raise HTTPException(401, "Invalid admin token")
    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=hours_ahead)
    query = select(Match).where(Match.kickoff_at > now, Match.kickoff_at <= end).order_by(Match.kickoff_at)
    if season is not None:
        query = query.where(Match.season == season)
    matches = (await db.execute(query)).scalars().all()
    selected = []
    for match in matches:
        row = (await db.execute(select(OraclePrediction).where(OraclePrediction.match_id == match.id))).scalar_one_or_none()
        if force or not _is_ai_payload(_payload_from_row(row)):
            selected.append(match)
        if len(selected) >= batch_size:
            break
    if not selected:
        return {"requested": 0, "generated": 0, "message": "No Oracle prediction needs generation"}
    result = await generate_or_refresh_matches(db, selected, force=force)
    return {**result, "match_ids": [m.id for m in selected], "batch_size": batch_size, "hours_ahead": hours_ahead}


@router.get("/matches/{match_id}")
async def oracle_prediction(match_id: int, db: AsyncSession = Depends(get_db)):
    match = await db.get(Match, match_id)
    if match is None:
        raise HTTPException(404, "Match not found")

    now = datetime.now(timezone.utc)
    if match.kickoff_at <= now:
        cached = await _get_cache(db, match_id)
        if cached:
            return cached
        raise HTTPException(409, "Оракул не успел сделать прогноз до начала матча")

    # One match can be opened by many users at once. Only the first request may
    # contact OpenAI; the rest wait for the same cached result.
    async with _match_lock(match_id):
        match = await db.get(Match, match_id)
        item = await _refresh_one_context(db, match, force=False)
        if item["status"] == "cache-unchanged":
            cached = await _get_cache(db, match_id)
            if cached:
                return cached

        result = await _ai_analyze_batch([item])
        ai = result.get(match_id)
        if ai is None:
            # Never fall back to a local forecast. If an older real AI prediction
            # exists, keep serving it rather than replacing it with invented data.
            cached = await _get_cache(db, match_id)
            if cached:
                cached["refresh_failed"] = True
                cached["stale"] = True
                return cached
            raise HTTPException(503, "OpenAI сейчас недоступен. Попробуй открыть прогноз позже.")

        payload = _compose_payload(item["ctx"], ai, item["mode"])
        if not await _save_cache(db, match_id, payload, bump_generated=True):
            raise HTTPException(409, "Матч уже начался — прогноз больше нельзя обновить")
        await db.commit()
        payload["cached"] = False
        payload["generated_at"] = datetime.now(timezone.utc)
        payload["locked_at"] = match.kickoff_at
        return payload
