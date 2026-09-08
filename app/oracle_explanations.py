from __future__ import annotations

import app.oracle as oracle

EXPLANATION_VERSION = 3
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
    """Add richer explanations and lazy one-time output-format upgrades.

    Existing predictions are upgraded only when they are opened (or otherwise
    explicitly refreshed). This avoids re-analyzing the whole cache merely
    because the user-facing explanation format gained a clearer presentation.
    """
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original_normalize = oracle._normalize_ai
    original_previous = oracle._previous_forecast
    original_refresh = oracle._refresh_one_context
    original_compose = oracle._compose_payload

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

    def compose_with_explanation_version(ctx, ai, mode):
        payload = original_compose(ctx, ai, mode)
        payload["explanation_version"] = EXPLANATION_VERSION
        return payload

    async def refresh_with_output_upgrade(db, match, force=False):
        result = await original_refresh(db, match, force=force)
        previous = result.get("previous") if isinstance(result, dict) else None
        if not isinstance(previous, dict):
            return result

        missing_scenarios = _scenario(previous.get("match_scenarios")) is None
        old_explanation = int(previous.get("explanation_version") or 0) < EXPLANATION_VERSION
        if not missing_scenarios and not old_explanation:
            return result

        # Reuse the previous forecast and ask a delta request to fill only the
        # missing/richer explanation fields. If a real context delta already
        # exists, the same OpenAI call handles both jobs.
        output_request = dict(result.get("output_request") or {})
        if missing_scenarios:
            output_request["match_scenarios"] = True
        if old_explanation:
            output_request["key_factors_human"] = True
        result["output_request"] = output_request

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
    oracle._compose_payload = compose_with_explanation_version
    oracle._refresh_one_context = refresh_with_output_upgrade
