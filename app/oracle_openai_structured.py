import json
import logging

from openai import AsyncOpenAI

import app.oracle as oracle

logger = logging.getLogger(__name__)

_ORACLE_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "matches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "match_id": {"type": "integer"},
                    "unchanged": {"type": "boolean"},
                    "home_score": {"type": ["integer", "null"]},
                    "away_score": {"type": ["integer", "null"]},
                    "confidence": {"type": ["number", "null"]},
                    "data_quality": {
                        "type": ["string", "null"],
                        "enum": ["high", "medium", "low", None],
                    },
                    "probabilities": {
                        "anyOf": [
                            {
                                "type": "object",
                                "properties": {
                                    "home": {"type": "number"},
                                    "draw": {"type": "number"},
                                    "away": {"type": "number"},
                                },
                                "required": ["home", "draw", "away"],
                                "additionalProperties": False,
                            },
                            {"type": "null"},
                        ]
                    },
                    "reasoning": {"type": ["string", "null"]},
                    "key_factors": {
                        "anyOf": [
                            {"type": "array", "items": {"type": "string"}},
                            {"type": "null"},
                        ]
                    },
                    "failure_risks": {
                        "anyOf": [
                            {"type": "array", "items": {"type": "string"}},
                            {"type": "null"},
                        ]
                    },
                },
                "required": [
                    "match_id",
                    "unchanged",
                    "home_score",
                    "away_score",
                    "confidence",
                    "data_quality",
                    "probabilities",
                    "reasoning",
                    "key_factors",
                    "failure_risks",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["matches"],
    "additionalProperties": False,
}


async def _structured_ai_analyze_batch(items):
    """Oracle analysis with low reasoning + Structured Outputs.

    GPT-5 Mini can spend the output-token budget on reasoning before emitting
    visible text. Structured Outputs plus an explicit low reasoning effort and a
    larger output allowance prevents an otherwise successful Responses call from
    reaching the app with an empty output_text.
    """
    settings = oracle.settings
    if not settings.openai_oracle_enabled or not settings.openai_api_key or not items:
        return {}

    dynamic = []
    for item in items:
        row = {"match_id": item["ctx"]["match"].id, "mode": item["mode"]}
        if item["mode"] == "initial":
            row["context"] = item["ctx"]["snapshot"]
        else:
            row["previous_forecast"] = oracle._previous_forecast(item["previous"])
            row["changes"] = item["changes"]
        dynamic.append(row)

    instructions = (
        oracle.ANALYSIS_INSTRUCTIONS
        + "\nДополнение: поле unchanged обязательно. Для initial всегда unchanged=false и верни полный прогноз. "
        + "Для delta с unchanged=true остальные nullable-поля верни null."
    )
    prompt = instructions + "\nДанные для анализа:\n" + json.dumps(dynamic, ensure_ascii=False, default=str)

    try:
        async with oracle.ANALYSIS_LOCK:
            response = await AsyncOpenAI(api_key=settings.openai_api_key).responses.create(
                model=settings.openai_oracle_model,
                input=prompt,
                reasoning={"effort": "low"},
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "oracle_predictions",
                        "strict": True,
                        "schema": _ORACLE_RESPONSE_SCHEMA,
                    }
                },
                max_output_tokens=max(1800, 900 * len(items)),
            )

        output_text = (getattr(response, "output_text", None) or "").strip()
        if not output_text:
            logger.error(
                "Oracle OpenAI returned no output_text: status=%s incomplete=%s usage=%s",
                getattr(response, "status", None),
                getattr(response, "incomplete_details", None),
                getattr(response, "usage", None),
            )
            return {}

        raw = json.loads(output_text)
        rows = raw.get("matches") if isinstance(raw, dict) else None
        if not isinstance(rows, list):
            return {}

        valid = {item["ctx"]["match"].id: item for item in items}
        result = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            match_id = int(oracle._num(row.get("match_id")) or 0)
            item = valid.get(match_id)
            if not item:
                continue
            fallback = oracle._previous_forecast(item["previous"]) if item["mode"] == "delta" else None
            normalized = oracle._normalize_ai(row, fallback)
            if normalized:
                result[match_id] = normalized

        if getattr(response, "usage", None):
            logger.info("Oracle structured OpenAI usage: %s", response.usage)
        return result
    except Exception:
        logger.exception("Oracle structured analysis failed")
        return {}


def install_structured_oracle_openai() -> None:
    oracle._ai_analyze_batch = _structured_ai_analyze_batch
