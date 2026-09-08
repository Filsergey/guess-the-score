from __future__ import annotations

import logging
import re

import app.oracle as oracle
import app.oracle_h2h as weighted_h2h

logger = logging.getLogger(__name__)

_ORIGINAL_MATCH_CONTEXT = None
_INSTALLED = False


def _norm(value: str | None) -> str:
    text = str(value or "").casefold()
    text = re.sub(r"\b(fc|cf|fk|sc|afc|club|football|futbol)\b", " ", text)
    return re.sub(r"[^a-z0-9а-яё]+", "", text)


# Verified historical meetings used only when the normal DB/SStats/Flashscore
# layers return no H2H at all. Keep this registry deliberately small and sourced
# from authoritative competition/club records; it is not a prediction override.
_VERIFIED_H2H: dict[frozenset[str], list[dict]] = {
    frozenset((_norm("Барселона"), _norm("Фейеноорд"))): [
        {
            "date": "1974-11-05",
            "home": "Барселона",
            "away": "Фейеноорд",
            "score": "3:0",
            "competition": "European Cup 1974/75",
            "source": "UEFA verified history",
            "verification_url": "https://www.uefa.com/uefachampionsleague/match/63244--barcelona-vs-feyenoord/",
        },
        {
            "date": "1974-10-22",
            "home": "Фейеноорд",
            "away": "Барселона",
            "score": "0:0",
            "competition": "European Cup 1974/75",
            "source": "UEFA verified history",
            "verification_url": "https://www.uefa.com/uefachampionsleague/match/63243--feyenoord-vs-barcelona/",
        },
    ],
}


def _rows_for_pair(home_name: str, away_name: str) -> list[dict]:
    key = frozenset((_norm(home_name), _norm(away_name)))
    rows = _VERIFIED_H2H.get(key) or []
    if not rows:
        return []

    # Re-label the known canonical names with the names used by the app, while
    # preserving which side was home in the historical fixture.
    home_norm = _norm(home_name)
    away_norm = _norm(away_name)
    result = []
    for item in rows:
        row = dict(item)
        row_home_norm = _norm(row.get("home"))
        row_away_norm = _norm(row.get("away"))
        if row_home_norm == home_norm and row_away_norm == away_norm:
            row["home"], row["away"] = home_name, away_name
        elif row_home_norm == away_norm and row_away_norm == home_norm:
            row["home"], row["away"] = away_name, home_name
        result.append(row)
    return result


async def _match_context_with_verified_h2h(match, db):
    ctx = await _ORIGINAL_MATCH_CONTEXT(match, db)
    if ctx.get("head_to_head_matches"):
        return ctx

    home = ctx.get("home")
    away = ctx.get("away")
    home_name = getattr(home, "name", "Хозяева")
    away_name = getattr(away, "name", "Гости")
    rows = _rows_for_pair(home_name, away_name)
    if not rows:
        return ctx

    rows = [row for row in rows if str(row.get("date") or "") < match.kickoff_at.date().isoformat()]
    if not rows:
        return ctx

    metrics = weighted_h2h._h2h_metrics(rows, home_name, away_name, match.kickoff_at)
    ctx["head_to_head_matches"] = rows
    ctx["head_to_head_metrics"] = metrics
    ctx["head_to_head_source"] = "uefa-verified"

    snapshot = dict(ctx.get("snapshot") or {})
    snapshot.pop("head_to_head_matches", None)
    snapshot["head_to_head"] = metrics
    ctx["snapshot"] = snapshot
    ctx["context_hash"] = oracle._canonical_hash(snapshot)

    logger.warning(
        "Oracle H2H verified fallback: %s-%s rows=%s relevance=%s influence=%s",
        home_name,
        away_name,
        len(rows),
        metrics.get("relevance_pct"),
        metrics.get("effective_weight_pct"),
    )
    return ctx


def install_oracle_h2h_verified() -> None:
    global _ORIGINAL_MATCH_CONTEXT, _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    _ORIGINAL_MATCH_CONTEXT = oracle._match_context
    oracle._match_context = _match_context_with_verified_h2h
