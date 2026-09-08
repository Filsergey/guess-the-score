from __future__ import annotations

from datetime import datetime, timezone

import app.oracle as oracle

_MAX_MATCHES = 5
_MAX_INFLUENCE_PCT = 10.0
_ORIGINAL_MATCH_CONTEXT = None
_ORIGINAL_COMPOSE_PAYLOAD = None
_INSTALLED = False


def _parse_score(value) -> tuple[int, int] | None:
    try:
        left, right = str(value or "").split(":", 1)
        return int(left), int(right)
    except (TypeError, ValueError):
        return None


def _parse_date(value) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _recency_weight(age_days: int) -> float:
    years = max(0.0, float(age_days) / 365.25)
    if years <= 1:
        return 1.0
    if years <= 2:
        return 0.80
    if years <= 3:
        return 0.60
    if years <= 5:
        return 0.35
    if years <= 10:
        return 0.10
    return 0.02


def _empty_metrics() -> dict:
    return {
        "count": 0,
        "home_wins": 0,
        "draws": 0,
        "away_wins": 0,
        "home_goals": 0,
        "away_goals": 0,
        "avg_total_goals": None,
        "btts_rate": None,
        "over_2_5_rate": None,
        "sample_factor": 0.0,
        "recency_factor": 0.0,
        "relevance": 0.0,
        "relevance_pct": 0.0,
        "max_influence_pct": _MAX_INFLUENCE_PCT,
        "effective_influence_pct": 0.0,
        "latest_age_days": None,
        "oldest_age_days": None,
        "quality": "none",
    }


def _h2h_metrics(rows: list[dict], home_name: str, away_name: str, before: datetime) -> dict:
    if not rows:
        return _empty_metrics()

    before_utc = before
    if before_utc.tzinfo is None:
        before_utc = before_utc.replace(tzinfo=timezone.utc)
    before_utc = before_utc.astimezone(timezone.utc)

    home_wins = draws = away_wins = 0
    home_goals = away_goals = 0
    btts = overs = 0
    age_days_list: list[int] = []
    recency_weights: list[float] = []
    valid = 0

    for row in rows[:_MAX_MATCHES]:
        score = _parse_score(row.get("score"))
        played_at = _parse_date(row.get("date"))
        if score is None or played_at is None:
            continue

        raw_home_goals, raw_away_goals = score
        row_home = str(row.get("home") or "").casefold()
        row_away = str(row.get("away") or "").casefold()
        wanted_home = str(home_name or "").casefold()
        wanted_away = str(away_name or "").casefold()

        if row_home == wanted_home and row_away == wanted_away:
            own, opp = raw_home_goals, raw_away_goals
        elif row_home == wanted_away and row_away == wanted_home:
            own, opp = raw_away_goals, raw_home_goals
        else:
            # Rows originate from the exact home/away team-id query in oracle.py.
            # If names differ because of provider/localization aliases, infer the
            # current home side from whichever participant matches it.
            if row_home == wanted_home:
                own, opp = raw_home_goals, raw_away_goals
            elif row_away == wanted_home:
                own, opp = raw_away_goals, raw_home_goals
            else:
                continue

        age_days = max(0, (before_utc.date() - played_at.date()).days)
        age_days_list.append(age_days)
        recency_weights.append(_recency_weight(age_days))
        valid += 1
        home_goals += own
        away_goals += opp
        btts += int(own > 0 and opp > 0)
        overs += int(own + opp >= 3)
        if own > opp:
            home_wins += 1
        elif own < opp:
            away_wins += 1
        else:
            draws += 1

    if not valid:
        return _empty_metrics()

    sample_factor = min(1.0, valid / float(_MAX_MATCHES))
    recency_factor = sum(recency_weights) / valid
    relevance = max(0.0, min(1.0, sample_factor * recency_factor))
    effective = _MAX_INFLUENCE_PCT * relevance
    if relevance >= 0.60 and valid >= 4:
        quality = "high"
    elif relevance >= 0.25 and valid >= 2:
        quality = "medium"
    else:
        quality = "low"

    return {
        "count": valid,
        "home_wins": home_wins,
        "draws": draws,
        "away_wins": away_wins,
        "home_goals": home_goals,
        "away_goals": away_goals,
        "avg_total_goals": round((home_goals + away_goals) / valid, 2),
        "btts_rate": round(btts / valid, 2),
        "over_2_5_rate": round(overs / valid, 2),
        "sample_factor": round(sample_factor, 3),
        "recency_factor": round(recency_factor, 3),
        "relevance": round(relevance, 3),
        "relevance_pct": round(relevance * 100, 1),
        "max_influence_pct": _MAX_INFLUENCE_PCT,
        "effective_influence_pct": round(effective, 2),
        "latest_age_days": min(age_days_list),
        "oldest_age_days": max(age_days_list),
        "quality": quality,
    }


def _summary(metrics: dict) -> str:
    if not metrics or not metrics.get("count"):
        return "В нашей базе нет завершённых очных встреч до этого матча."
    return (
        f"Последние {metrics['count']} очных встреч: "
        f"{metrics['home_wins']} побед хозяев, {metrics['draws']} ничьих, "
        f"{metrics['away_wins']} побед гостей; голы {metrics['home_goals']}:{metrics['away_goals']}. "
        f"Актуальность H2H {metrics['relevance_pct']}%, поэтому его допустимое влияние "
        f"на прогноз ограничено {metrics['effective_influence_pct']}%."
    )


async def _match_context_with_weighted_h2h(match, db):
    ctx = await _ORIGINAL_MATCH_CONTEXT(match, db)
    rows = list(ctx.get("head_to_head_matches") or [])
    home = ctx.get("home")
    away = ctx.get("away")
    metrics = _h2h_metrics(
        rows,
        getattr(home, "name", "Хозяева"),
        getattr(away, "name", "Гости"),
        match.kickoff_at,
    )
    ctx["head_to_head_metrics"] = metrics

    # Keep full rows in ctx for the UI, but do not send them to OpenAI. The model
    # receives only compact server-computed metrics, which is cheaper and prevents
    # ancient H2H from being overinterpreted.
    snapshot = dict(ctx.get("snapshot") or {})
    snapshot.pop("head_to_head_matches", None)
    snapshot["head_to_head"] = metrics
    ctx["snapshot"] = snapshot
    ctx["context_hash"] = oracle._canonical_hash(snapshot)
    return ctx


def _compose_payload_with_weighted_h2h(ctx, ai, mode):
    payload = _ORIGINAL_COMPOSE_PAYLOAD(ctx, ai, mode)
    metrics = dict(ctx.get("head_to_head_metrics") or _empty_metrics())
    payload["head_to_head_metrics"] = metrics
    payload["head_to_head"] = _summary(metrics)
    return payload


def install_oracle_h2h() -> None:
    global _INSTALLED, _ORIGINAL_MATCH_CONTEXT, _ORIGINAL_COMPOSE_PAYLOAD
    if _INSTALLED:
        return
    _INSTALLED = True
    _ORIGINAL_MATCH_CONTEXT = oracle._match_context
    _ORIGINAL_COMPOSE_PAYLOAD = oracle._compose_payload
    oracle._match_context = _match_context_with_weighted_h2h
    oracle._compose_payload = _compose_payload_with_weighted_h2h
    oracle.ANALYSIS_INSTRUCTIONS += """

Правило H2H: поле context.head_to_head уже агрегировано сервером. Считай H2H только вспомогательным фактором. Поле effective_influence_pct — верхняя граница его влияния на итоговый прогноз; не превышай её. relevance_pct отражает актуальность с учётом давности и количества встреч. Если relevance_pct близко к нулю, считай H2H практически нейтральным и не используй старые матчи как аргумент для сильного изменения счёта или вероятностей."""
