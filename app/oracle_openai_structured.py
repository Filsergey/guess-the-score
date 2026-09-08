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
                            {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 4,
                                "maxItems": 10,
                            },
                            {"type": "null"},
                        ]
                    },
                    "match_scenarios": {
                        "anyOf": [
                            {
                                "type": "object",
                                "properties": {
                                    "base": {"type": "string"},
                                    "alternative": {"type": "string"},
                                },
                                "required": ["base", "alternative"],
                                "additionalProperties": False,
                            },
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
                    "match_scenarios",
                    "failure_risks",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["matches"],
    "additionalProperties": False,
}


def _explanation_context(snapshot: dict) -> dict:
    """Small factual subset used only for one-time explanation upgrades."""
    if not isinstance(snapshot, dict):
        return {}
    keys = (
        "match",
        "uefa_club_coefficient",
        "bookmaker_market",
        "last_10",
        "signals",
        "form",
        "head_to_head_matches",
        "standings",
    )
    return {key: snapshot[key] for key in keys if key in snapshot}


async def _structured_ai_analyze_batch(items):
    """Oracle analysis with low reasoning + Structured Outputs."""
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
            if item.get("output_request"):
                row["output_request"] = item["output_request"]
                if item["output_request"].get("key_factors_v2"):
                    row["explanation_context"] = _explanation_context(item["ctx"].get("snapshot") or {})
        dynamic.append(row)

    instructions = (
        oracle.ANALYSIS_INSTRUCTIONS
        + "\n\nТребования к объяснению прогноза:"
        + "\n1. reasoning — 3–5 конкретных предложений, максимум около 700 символов. Объясни, кто сильнее, почему выбран такой сценарий и где главный риск."
        + "\n2. key_factors — 6–10 коротких, полезных пользователю факторов с КОНКРЕТНЫМИ цифрами из context/explanation_context. Не ограничивайся только факторами, которые изменили итоговый счёт: покажи и важные информационные показатели матча."
        + "\nЕсли соответствующие данные доступны, обязательно отдельными пунктами покажи:"
        + "\n— UEFA club coefficient обеих команд: rank и coefficient;"
        + "\n— рынок Match Winner 1X2: размер панели букмекеров и Home/Draw/Away avg_odds с implied_pct;"
        + "\n— рынок Home/Away: коэффициенты и implied_pct;"
        + "\n— последние 10 матчей хозяев: W-D-L и goals_for:goals_against;"
        + "\n— последние 10 матчей гостей: W-D-L и goals_for:goals_against;"
        + "\n— Goals Over/Under 1.5 и 2.5: доступные коэффициенты и implied_pct, плюс короткий вывод о результативности;"
        + "\n— BTTS Yes/No: доступные коэффициенты и implied_pct, плюс короткий вывод;"
        + "\nПосле этого, если есть место и данные действительно полезны, добавь xG/Glicko, H2H и положение в таблице."
        + "\nПоле avg_odds в bookmaker_market фактически является медианой стабильной панели букмекеров. implied_pct содержит маржу. Не суммируй эти проценты как честные вероятности и не выдумывай отсутствующие рынки."
        + "\n3. match_scenarios.base — базовый сценарий матча в 1–2 предложениях. match_scenarios.alternative — реалистичный альтернативный сценарий в 1–2 предложениях."
        + "\n4. failure_risks — 2–4 коротких риска, которые могут сломать прогноз."
        + "\nНе повторяй один и тот же тезис дословно в reasoning, key_factors и scenarios."
        + "\nПоле unchanged обязательно. Для initial всегда unchanged=false и верни полный прогноз, включая reasoning, key_factors, match_scenarios и failure_risks."
        + "\nДля обычного delta: если изменения несущественны для прогноза, верни unchanged=true, а остальные nullable-поля — null. Если прогноз меняется, верни только нужные изменившиеся поля, остальные nullable-поля можно вернуть null."
        + "\nЕсли присутствует output_request.match_scenarios=true или output_request.key_factors_v2=true, это одноразовое обновление формата старого прогноза. Не меняй счёт, вероятности, confidence, reasoning или риски без реальной причины. Верни unchanged=false; заполни только запрошенные поля (match_scenarios и/или key_factors), остальные неизменившиеся nullable-поля верни null."
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
                max_output_tokens=max(2500, 1250 * len(items)),
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
