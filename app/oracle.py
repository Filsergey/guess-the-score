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
from app.oracle_news_models import OracleTeamNews
from app.providers.sstats import SStatsProvider

router = APIRouter(prefix="/api/oracle", tags=["oracle"])
settings = get_settings()
logger = logging.getLogger(__name__)
CACHE_SCHEMA_VERSION = 4
MIN_READABLE_CACHE_VERSION = 3
ANALYSIS_LOCK = asyncio.Lock()

ANALYSIS_INSTRUCTIONS = """Ты футбольный аналитик приложения «Угадай счёт».
Ты НЕ ищешь данные в интернете. Используй только структурированные данные сервера.
Сервер уже собрал последние матчи, H2H, форму, xG/Glicko, коэффициенты, турнирный контекст и отдельно закешированные новости команд.
Не выдумывай отсутствующие факты. Если данных мало — снижай confidence/data_quality.
Верни ТОЛЬКО JSON без markdown:
{"matches":[{"match_id":123,"home_score":1,"away_score":1,"confidence":60,"data_quality":"high|medium|low","probabilities":{"home":30,"draw":35,"away":35},"reasoning":"2-4 конкретных предложения по-русски","key_factors":["3-5 факторов"],"failure_risks":["2-4 риска"]}]}
Вероятности должны суммироваться до 100. Счёт — целые числа 0..20.
При delta-обновлении передаются предыдущий прогноз и ТОЛЬКО изменившиеся поля контекста. Меняй прогноз только если изменение действительно влияет на матч."""

NEWS_INSTRUCTIONS = """Ты собираешь только свежий командный контекст перед футбольными матчами.
Проверь подтверждённые травмы, дисквалификации, ожидаемую ротацию/состав и действительно важные свежие новости.
Не собирай результаты последних матчей, H2H, xG, коэффициенты и таблицу — приложение получает это само.
Не выдумывай. Если подтверждений нет, возвращай пустые массивы.
Верни ТОЛЬКО JSON без markdown:
{"teams":[{"team_id":1,"summary":"кратко или пустая строка","injuries":["..."],"suspensions":["..."],"rotation":["..."]}]}"""


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


def _score(home_xg, away_xg):
    def one(x):
        return min(6, max(0, int(math.floor(max(0.15, min(4.5, x)) + 0.35))))
    return one(home_xg), one(away_xg)


def _odds_probs(home, draw, away):
    values = [_num(home), _num(draw), _num(away)]
    if not all(x and x > 1 for x in values):
        return None
    inverse = [1 / x for x in values]
    total = sum(inverse)
    return [x / total for x in inverse]


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
        a, b = (match.home_goals, match.away_goals) if match.home_team_id == team_id else (match.away_goals, match.home_goals)
        gf += a
        ga += b
        pts += 3 if a > b else (1 if a == b else 0)
    n = len(rows)
    return {"count": n, "gf": round(gf / n, 2), "ga": round(ga / n, 2), "ppg": round(pts / n, 2)}


def _form_xg(home_form, away_form):
    if home_form["count"] < 2 or away_form["count"] < 2:
        return None, None
    return (
        max(0.2, min(3.8, (home_form["gf"] + away_form["ga"]) / 2 * 1.08)),
        max(0.2, min(3.8, (away_form["gf"] + home_form["ga"]) / 2)),
    )


async def _name_maps(db, matches):
    team_ids = {m.home_team_id for m in matches} | {m.away_team_id for m in matches}
    tournament_ids = {m.tournament_id for m in matches}
    teams = (await db.execute(select(Team).where(Team.id.in_(team_ids)))).scalars().all() if team_ids else []
    tournaments = (await db.execute(select(Tournament).where(Tournament.id.in_(tournament_ids)))).scalars().all() if tournament_ids else []
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
        for team_id, gf, ga in ((row.home_team_id, row.home_goals, row.away_goals), (row.away_team_id, row.away_goals, row.home_goals)):
            item = stats.setdefault(team_id, {"played": 0, "points": 0, "gf": 0, "ga": 0})
            item["played"] += 1
            item["gf"] += gf
            item["ga"] += ga
            item["points"] += 3 if gf > ga else (1 if gf == ga else 0)
    ordered = sorted(stats.items(), key=lambda x: (x[1]["points"], x[1]["gf"] - x[1]["ga"], x[1]["gf"]), reverse=True)
    places = {team_id: index + 1 for index, (team_id, _) in enumerate(ordered)}

    def one(team_id):
        item = stats.get(team_id, {"played": 0, "points": 0, "gf": 0, "ga": 0})
        return {**item, "place": places.get(team_id)}

    return {"home": one(match.home_team_id), "away": one(match.away_team_id)}


def _json_text(text):
    value = (text or "").strip()
    if "{" in value and "}" in value:
        value = value[value.find("{"):value.rfind("}") + 1]
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


async def _team_news_rows(db, team_ids):
    if not team_ids:
        return {}
    rows = (await db.execute(select(OracleTeamNews).where(OracleTeamNews.team_id.in_(team_ids)))).scalars().all()
    return {row.team_id: row for row in rows}


def _normalize_news_item(row):
    return {
        "summary": _clean_text(row.get("summary")) or "",
        "injuries": _strings(row.get("injuries")),
        "suspensions": _strings(row.get("suspensions")),
        "rotation": _strings(row.get("rotation")),
    }


async def _web_team_news_batch(teams):
    if not settings.openai_oracle_enabled or not settings.openai_api_key or not settings.oracle_news_enabled or not teams:
        return {}
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    dynamic = [{"team_id": team.id, "team": team.name} for team in teams]
    prompt = NEWS_INSTRUCTIONS + "\nКоманды для проверки:\n" + json.dumps(dynamic, ensure_ascii=False)
    try:
        response = await client.responses.create(
            model=settings.openai_oracle_model,
            tools=[{"type": "web_search"}],
            tool_choice="auto",
            input=prompt,
            max_output_tokens=900,
        )
        raw = _json_text(response.output_text)
        rows = raw.get("teams") if isinstance(raw, dict) else None
        if not isinstance(rows, list):
            return {}
        valid = {team.id for team in teams}
        result = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            team_id = int(_num(row.get("team_id")) or 0)
            if team_id in valid:
                result[team_id] = _normalize_news_item(row)
        if getattr(response, "usage", None):
            logger.info("Oracle team-news OpenAI usage: %s", response.usage)
        return result
    except Exception:
        logger.exception("Oracle team-news lookup failed")
        return {}


async def _refresh_team_news_for_matches(matches, db, force=False):
    if not settings.oracle_news_enabled:
        return {}
    now = datetime.now(timezone.utc)
    window = timedelta(hours=max(1, settings.oracle_news_window_hours))
    relevant = [m for m in matches if now < m.kickoff_at <= now + window]
    if not relevant:
        return {}
    team_ids = {m.home_team_id for m in relevant} | {m.away_team_id for m in relevant}
    teams = {team.id: team for team in (await db.execute(select(Team).where(Team.id.in_(team_ids)))).scalars().all()}
    cached = await _team_news_rows(db, team_ids)
    soonest = {}
    for match in relevant:
        for team_id in (match.home_team_id, match.away_team_id):
            soonest[team_id] = min(soonest.get(team_id, match.kickoff_at), match.kickoff_at)
    due = []
    for team_id in team_ids:
        row = cached.get(team_id)
        age = now - row.generated_at if row else None
        final_due = bool(row and soonest[team_id] - now <= timedelta(hours=2) and age >= timedelta(hours=max(1, settings.oracle_news_final_refresh_hours)))
        if force or row is None or row.expires_at <= now or final_due:
            if teams.get(team_id):
                due.append(teams[team_id])
    if not due:
        return cached
    due = due[:max(1, settings.oracle_news_batch_size)]
    fresh = await _web_team_news_batch(due)
    ttl = timedelta(hours=max(1, settings.oracle_news_refresh_hours))
    for team in due:
        data = fresh.get(team.id)
        if data is None:
            continue
        content_hash = _canonical_hash(data)
        row = cached.get(team.id)
        if row is None:
            row = OracleTeamNews(team_id=team.id, payload_json=json.dumps(data, ensure_ascii=False), content_hash=content_hash, generated_at=now, expires_at=now + ttl, updated_at=now)
            db.add(row)
            cached[team.id] = row
        else:
            row.payload_json = json.dumps(data, ensure_ascii=False)
            row.content_hash = content_hash
            row.generated_at = now
            row.expires_at = now + ttl
            row.updated_at = now
    await db.flush()
    return cached


def _news_payload(row):
    if row is None:
        return {"hash": None, "summary": "", "injuries": [], "suspensions": [], "rotation": []}
    try:
        data = json.loads(row.payload_json)
    except Exception:
        data = {}
    normalized = _normalize_news_item(data if isinstance(data, dict) else {})
    return {"hash": row.content_hash, **normalized}


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
    news_rows = await _team_news_rows(db, {match.home_team_id, match.away_team_id})
    news = {"home": _news_payload(news_rows.get(match.home_team_id)), "away": _news_payload(news_rows.get(match.away_team_id))}
    snapshot = {
        "match": {"match_id": match.id, "home": home.name if home else "Хозяева", "away": away.name if away else "Гости", "kickoff_at": match.kickoff_at.isoformat(), "season": match.season, "round": match.round_name},
        "signals": signals,
        "form": {"home": home_form, "away": away_form},
        "recent_matches": recent,
        "head_to_head_matches": h2h,
        "standings": standings,
        "team_news": news,
    }
    return {"match": match, "home": home, "away": away, "signals": signals, "home_form": home_form, "away_form": away_form, "recent_matches": recent, "head_to_head_matches": h2h, "standings": standings, "team_news": news, "errors": errors, "snapshot": snapshot, "context_hash": _canonical_hash(snapshot)}


def _form_text(form):
    if not form or not form.get("count"):
        return "нет достаточных данных"
    return f"{form['count']} матч.: {form['gf']:.2f} забито, {form['ga']:.2f} пропущено, {form['ppg']:.2f} очка/игру"


def _h2h_summary(rows):
    if not rows:
        return "В нашей базе нет завершённых очных встреч до этого матча."
    last = rows[0]
    return f"В базе найдено {len(rows)} последних очных встреч. Последняя: {last['date']} — {last['home']} — {last['away']} {last['score']}."


def _local_forecast(ctx):
    signals, home_form, away_form = ctx["signals"], ctx["home_form"], ctx["away_form"]
    form_home_xg, form_away_xg = _form_xg(home_form, away_form)
    raw_home = signals["glicko_xg"]["home"] or signals["odds_xg"]["home"]
    raw_away = signals["glicko_xg"]["away"] or signals["odds_xg"]["away"]
    hp, ap = signals["glicko_win_probability"]["home"], signals["glicko_win_probability"]["away"]
    odds = _odds_probs(signals["odds"]["home"], signals["odds"]["draw"], signals["odds"]["away"])
    home_xg, away_xg, used_form = raw_home, raw_away, False
    if home_xg is None or away_xg is None:
        if form_home_xg is not None:
            home_xg, away_xg, used_form = form_home_xg, form_away_xg, True
        elif hp is not None and ap is not None:
            home_xg, away_xg = 1.15 + 1.35 * hp, 1.15 + 1.35 * ap
        elif odds:
            home_xg, away_xg = 1 + 1.55 * odds[0], 1 + 1.55 * odds[2]
        else:
            home_xg = away_xg = 1.15
    home_score, away_score = _score(home_xg, away_xg)
    probs = odds
    if probs is None and form_home_xg is not None:
        diff = home_xg - away_xg
        ph = max(0.18, min(0.62, 0.36 + diff * 0.12))
        pa = max(0.18, min(0.62, 0.34 - diff * 0.12))
        pd = max(0.18, 1 - ph - pa)
        total = ph + pd + pa
        probs = [ph / total, pd / total, pa / total]
    factors = []
    if raw_home is not None and raw_away is not None:
        factors.append(f"xG/Glicko: {raw_home:.2f} — {raw_away:.2f}")
    elif used_form:
        factors.append(f"Оценка по форме: {home_xg:.2f} — {away_xg:.2f}")
    if odds:
        factors.append(f"Рынок 1/X/2: {odds[0] * 100:.0f}% / {odds[1] * 100:.0f}% / {odds[2] * 100:.0f}%")
    hs, as_ = ctx["standings"]["home"], ctx["standings"]["away"]
    if hs.get("place") and as_.get("place"):
        factors.append(f"Таблица: хозяева {hs['place']}-е, гости {as_['place']}-е")
    injuries = []
    for side, team in (("home", ctx["home"]), ("away", ctx["away"])):
        label = team.name if team else ("Хозяева" if side == "home" else "Гости")
        news = ctx["team_news"][side]
        injuries.extend([f"{label}: {x}" for x in news.get("injuries", [])])
        injuries.extend([f"{label}: {x}" for x in news.get("suspensions", [])])
    confidence = max(35, min(82, round(max(probs) * 100) if probs else 42))
    quality = "high" if raw_home is not None and raw_away is not None and probs else ("medium" if form_home_xg is not None else "low")
    return {
        "home_score": home_score,
        "away_score": away_score,
        "outcome": "home" if home_score > away_score else ("away" if away_score > home_score else "draw"),
        "confidence": confidence,
        "data_quality": quality,
        "xg": {"home": round(home_xg, 2), "away": round(away_xg, 2)},
        "probabilities": {"home": round(probs[0] * 100, 1), "draw": round(probs[1] * 100, 1), "away": round(probs[2] * 100, 1)} if probs else None,
        "reasoning": "Базовый прогноз рассчитан по SStats и нашей базе. OpenAI используется только для компактного анализа уже собранных данных.",
        "form": {"home": _form_text(home_form), "away": _form_text(away_form)},
        "recent_matches": ctx["recent_matches"],
        "head_to_head": _h2h_summary(ctx["head_to_head_matches"]),
        "head_to_head_matches": ctx["head_to_head_matches"],
        "injuries": injuries,
        "key_factors": factors or ["Недостаточно данных для сильного сигнала"],
        "failure_risks": ["Изменения состава и поздние новости могут изменить баланс"],
    }


def _normalize_ai(row, fallback):
    raw_home, raw_away = _num(row.get("home_score")), _num(row.get("away_score"))
    home_score = max(0, min(20, int(raw_home if raw_home is not None else fallback["home_score"])))
    away_score = max(0, min(20, int(raw_away if raw_away is not None else fallback["away_score"])))
    probs = row.get("probabilities") if isinstance(row.get("probabilities"), dict) else {}
    ph, pd, pa = _num(probs.get("home")), _num(probs.get("draw")), _num(probs.get("away"))
    if all(x is not None and x >= 0 for x in (ph, pd, pa)) and ph + pd + pa > 0:
        total = ph + pd + pa
        probabilities = {"home": round(ph * 100 / total, 1), "draw": round(pd * 100 / total, 1), "away": round(pa * 100 / total, 1)}
    else:
        probabilities = fallback.get("probabilities")
    raw_conf = _num(row.get("confidence"))
    confidence = max(0, min(100, int(raw_conf if raw_conf is not None else fallback["confidence"])))
    quality = str(row.get("data_quality") or fallback["data_quality"]).lower()
    if quality not in {"high", "medium", "low"}:
        quality = fallback["data_quality"]
    return {
        "home_score": home_score,
        "away_score": away_score,
        "outcome": "home" if home_score > away_score else ("away" if away_score > home_score else "draw"),
        "confidence": confidence,
        "data_quality": quality,
        "probabilities": probabilities,
        "reasoning": _clean_text(row.get("reasoning")) or fallback["reasoning"],
        "key_factors": _strings(row.get("key_factors"), 6) or fallback["key_factors"],
        "failure_risks": _strings(row.get("failure_risks"), 5) or fallback["failure_risks"],
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
    return {key: payload.get(key) for key in ("home_score", "away_score", "confidence", "data_quality", "probabilities", "reasoning", "key_factors", "failure_risks")}


async def _ai_analyze_batch(items):
    if not settings.openai_oracle_enabled or not settings.openai_api_key or not items:
        return {}
    dynamic = []
    for item in items:
        row = {
            "match_id": item["ctx"]["match"].id,
            "mode": item["mode"],
            "local_forecast": {key: item["local"].get(key) for key in ("home_score", "away_score", "confidence", "probabilities", "xg")},
        }
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
                max_output_tokens=max(900, 500 * len(items)),
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
            if item:
                result[match_id] = _normalize_ai(row, item["local"])
        if getattr(response, "usage", None):
            logger.info("Oracle analysis OpenAI usage: %s", response.usage)
        return result
    except Exception:
        logger.exception("Oracle analysis failed")
        return {}


def _compose_payload(ctx, local, ai=None, mode=None):
    now = datetime.now(timezone.utc).isoformat()
    result = dict(local)
    if ai:
        result.update(ai)
    result.update({
        "schema_version": CACHE_SCHEMA_VERSION,
        "match_id": ctx["match"].id,
        "source": "openai-analysis" if ai else "local-model",
        "details_errors": ctx["errors"],
        "context_hash": ctx["context_hash"],
        "analysis_context_hash": ctx["context_hash"] if ai else None,
        "context_snapshot": ctx["snapshot"],
        "context_checked_at": now,
        "ai_analyzed_at": now if ai else None,
        "ai_mode": mode if ai else None,
        "team_news_hashes": {"home": ctx["team_news"]["home"].get("hash"), "away": ctx["team_news"]["away"].get("hash")},
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
        row = OraclePrediction(match_id=match_id, payload_json=payload, source=data.get("source", "local-model"), generated_at=now, locked_at=match.kickoff_at, updated_at=now)
        db.add(row)
    else:
        row.payload_json = payload
        row.source = data.get("source", row.source or "local-model")
        if bump_generated:
            row.generated_at = now
        row.locked_at = match.kickoff_at
        row.updated_at = now
    return True


async def _get_cache(db, match_id):
    row = (await db.execute(select(OraclePrediction).where(OraclePrediction.match_id == match_id))).scalar_one_or_none()
    if not row:
        return None
    data = _payload_from_row(row)
    if not data or int(data.get("schema_version") or 0) < MIN_READABLE_CACHE_VERSION:
        return None
    data.pop("sources", None)
    data["cached"] = True
    data["generated_at"] = row.generated_at
    data["locked_at"] = row.locked_at
    return data


def _needs_refresh(match, cache_row, now):
    if match.kickoff_at <= now:
        return False
    if cache_row is None:
        return True
    payload = _payload_from_row(cache_row)
    if not payload or int(payload.get("schema_version") or 0) < CACHE_SCHEMA_VERSION:
        return True
    checked_raw = payload.get("context_checked_at")
    if not checked_raw:
        return True
    try:
        checked = datetime.fromisoformat(str(checked_raw).replace("Z", "+00:00"))
    except Exception:
        return True
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=timezone.utc)
    until = match.kickoff_at - now
    if until > timedelta(hours=72):
        interval = timedelta(hours=24)
    elif until > timedelta(hours=24):
        interval = timedelta(hours=12)
    elif until > timedelta(hours=6):
        interval = timedelta(hours=4)
    else:
        interval = timedelta(hours=1)
    return now - checked >= interval


async def _refresh_one_context(db, match, force=False):
    row = (await db.execute(select(OraclePrediction).where(OraclePrediction.match_id == match.id))).scalar_one_or_none()
    previous = _payload_from_row(row)
    ctx = await _match_context(match, db)
    local = _local_forecast(ctx)
    analysis_hash = previous.get("analysis_context_hash") if isinstance(previous, dict) else None
    if analysis_hash is None and previous and previous.get("ai_analyzed_at"):
        analysis_hash = previous.get("context_hash")
    already_ai = bool(previous and previous.get("ai_analyzed_at"))
    changed_since_analysis = analysis_hash != ctx["context_hash"]
    needs_ai = force or not already_ai or changed_since_analysis
    if not needs_ai:
        previous["context_checked_at"] = datetime.now(timezone.utc).isoformat()
        previous["context_snapshot"] = ctx["snapshot"]
        previous["context_hash"] = ctx["context_hash"]
        previous["team_news_hashes"] = {"home": ctx["team_news"]["home"].get("hash"), "away": ctx["team_news"]["away"].get("hash")}
        await _save_cache(db, match.id, previous, bump_generated=False)
        return {"match_id": match.id, "status": "cache-unchanged", "ai": False}
    if previous and previous.get("context_snapshot") and changed_since_analysis and not force:
        mode = "delta"
        changes = _diff_context(previous["context_snapshot"], ctx["snapshot"]) or {}
    else:
        mode, changes = "initial", None
    return {"match_id": match.id, "status": "needs-ai", "ai": True, "ctx": ctx, "local": local, "previous": previous, "changes": changes, "mode": mode}


async def generate_or_refresh_matches(db, matches, force=False, refresh_news=True):
    if not matches:
        return {"requested": 0, "generated": 0, "unchanged": 0, "local_only": 0}
    if refresh_news:
        await _refresh_team_news_for_matches(matches, db, force=False)
    work, unchanged = [], 0
    for match in matches:
        item = await _refresh_one_context(db, match, force=force)
        if item["status"] == "cache-unchanged":
            unchanged += 1
        else:
            work.append(item)
    ai_result = await _ai_analyze_batch(work)
    generated = local_only = 0
    for item in work:
        ctx = item["ctx"]
        ai = ai_result.get(item["match_id"])
        if ai is None and item["previous"] and item["previous"].get("ai_analyzed_at"):
            old = item["previous"]
            old["context_checked_at"] = datetime.now(timezone.utc).isoformat()
            old["context_snapshot"] = ctx["snapshot"]
            old["context_hash"] = ctx["context_hash"]
            old["team_news_hashes"] = {"home": ctx["team_news"]["home"].get("hash"), "away": ctx["team_news"]["away"].get("hash")}
            await _save_cache(db, item["match_id"], old, bump_generated=False)
            continue
        payload = _compose_payload(ctx, item["local"], ai, item["mode"] if ai else None)
        if ai:
            generated += 1
        else:
            local_only += 1
        await _save_cache(db, item["match_id"], payload, bump_generated=bool(ai))
    await db.commit()
    return {
        "requested": len(matches),
        "generated": generated,
        "unchanged": unchanged,
        "local_only": local_only,
        "ai_requested": len(work),
        "ai_modes": {"initial": sum(1 for x in work if x["mode"] == "initial"), "delta": sum(1 for x in work if x["mode"] == "delta")},
    }


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
        if force or _needs_refresh(match, row, now):
            selected.append(match)
        if len(selected) >= batch_size:
            break
    if not selected:
        return {"requested": 0, "generated": 0, "message": "No Oracle context needs checking"}
    result = await generate_or_refresh_matches(db, selected, force=force, refresh_news=True)
    return {**result, "match_ids": [m.id for m in selected], "batch_size": batch_size, "hours_ahead": hours_ahead}


@router.get("/matches/{match_id}")
async def oracle_prediction(match_id: int, db: AsyncSession = Depends(get_db)):
    match = await db.get(Match, match_id)
    if match is None:
        raise HTTPException(404, "Match not found")
    cached = await _get_cache(db, match_id)
    if cached:
        return cached
    if match.kickoff_at <= datetime.now(timezone.utc):
        raise HTTPException(409, "Оракул не успел сделать прогноз до начала матча")
    # Пользовательский GET больше никогда не запускает OpenAI/web_search.
    ctx = await _match_context(match, db)
    payload = _compose_payload(ctx, _local_forecast(ctx), ai=None)
    if await _save_cache(db, match_id, payload, bump_generated=False):
        await db.commit()
    payload["cached"] = False
    payload["locked_at"] = match.kickoff_at
    return payload
