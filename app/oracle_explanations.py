from __future__ import annotations

import app.oracle as oracle

_INSTALLED = False


def _scenario(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    base = oracle._clean_text(value.get("base"))
    alternative = oracle._clean_text(value.get("alternative"))
    if not base or not alternative:
        return None
    return {"base": base, "alternative": alternative}


def install_oracle_explanations() -> None:
    """Add match scenarios and one-time output-format upgrades to Oracle.

    Existing predictions are upgraded lazily only when they are opened (or
    otherwise explicitly refreshed). This avoids re-analyzing the whole cache
    just because the presentation schema gained a new field.
    """
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original_normalize = oracle._normalize_ai
    original_previous = oracle._previous_forecast
    original_refresh = oracle._refresh_one_context

    def normalize_with_scenarios(row, fallback=None):
        normalized = original_normalize(row, fallback)
        if normalized is None:
            return None
        current = _scenario(row.get("match_scenarios")) if isinstance(row, dict) else None
        if current is None and isinstance(fallback, dict):
            current = _scenario(fallback.get("match_scenarios"))
        if current is not None:
            normalized["match_scenarios"] = current
        return normalized

    def previous_with_scenarios(payload):
        previous = original_previous(payload)
        if previous is None:
            return None
        scenarios = _scenario(payload.get("match_scenarios")) if isinstance(payload, dict) else None
        if scenarios is not None:
            previous["match_scenarios"] = scenarios
        return previous

    async def refresh_with_output_upgrade(db, match, force=False):
        result = await original_refresh(db, match, force=force)
        previous = result.get("previous") if isinstance(result, dict) else None
        missing_scenarios = bool(
            isinstance(previous, dict)
            and _scenario(previous.get("match_scenarios")) is None
        )
        if not missing_scenarios:
            return result

        # Do not send the full context again just to gain a new explanation
        # field. Reuse the previous forecast and ask the delta request to fill
        # only the missing scenario text. If a real context delta already exists,
        # the same OpenAI call handles both jobs.
        result["output_request"] = {"match_scenarios": True}
        if result.get("status") == "cache-unchanged":
            result.update(
                {
                    "status": "needs-ai",
                    "ai": True,
                    "mode": "delta",
                    "changes": {},
                }
            )
        return result

    oracle._normalize_ai = normalize_with_scenarios
    oracle._previous_forecast = previous_with_scenarios
    oracle._refresh_one_context = refresh_with_output_upgrade
