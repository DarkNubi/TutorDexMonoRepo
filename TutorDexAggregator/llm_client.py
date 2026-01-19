import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

from logging_setup import bind_log_context, log_event, setup_logging, timed
from shared.config import load_aggregator_config


setup_logging()
logger = logging.getLogger("llm_client")
_CFG = load_aggregator_config()


def _safe_parse_json(json_string: str) -> Any:
    raw = json_string or ""

    try:
        from json_repair import repair_json  # type: ignore
    except Exception as e:
        raise RuntimeError("json-repair is required but not installed; run `pip install -r TutorDexAggregator/requirements.txt`") from e

    # Some versions support `return_objects=True`; use it if available (best-effort).
    try:
        import inspect

        if "return_objects" in inspect.signature(repair_json).parameters:
            return repair_json(raw, return_objects=True)
    except Exception as e:
        from shared.observability import swallow_exception
        swallow_exception(e, context="json_repair_return_objects", extra={"module": __name__})

    repaired = repair_json(raw)
    if isinstance(repaired, (dict, list)):
        return repaired
    if isinstance(repaired, str) and repaired.strip():
        return json.loads(repaired)
    raise RuntimeError("json-repair produced empty output")


def extract_json_object(text: str) -> Dict[str, Any]:
    t = (text or "").strip()
    t = t.strip("```").strip()
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output")
    candidate = t[start : end + 1]
    obj = _safe_parse_json(candidate)
    if not isinstance(obj, dict):
        raise ValueError("Parsed JSON is not an object")
    return obj


@dataclass(frozen=True)
class LlmConfig:
    api_url: str
    timeout_s: int = 200


def load_llm_config() -> LlmConfig:
    base = str(_CFG.llm_api_url or "http://localhost:1234").strip().rstrip("/")
    timeout_s = int(_CFG.llm_timeout_seconds or 200)
    return LlmConfig(api_url=base, timeout_s=timeout_s)


def chat_completion(
    *,
    model_name: str,
    system_prompt: str,
    user_content: str,
    cid: Optional[str] = None,
    channel: Optional[str] = None,
    step: str = "llm",
    temperature: float = 0.0,
) -> str:
    cfg = load_llm_config()
    url = f"{cfg.api_url}/v1/chat/completions"

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": (system_prompt or "").strip()},
        {"role": "user", "content": (user_content or "").strip()},
    ]
    payload: Dict[str, Any] = {"model": model_name, "messages": messages, "temperature": float(temperature)}

    with bind_log_context(cid=str(cid) if cid else None, channel=channel or None, step=step):
        log_event(logger, logging.INFO, "llm_call_start", model=model_name, url=url, prompt_chars=len(system_prompt or ""), user_chars=len(user_content or ""))
        t0 = timed()
        resp = requests.post(url, json=payload, timeout=cfg.timeout_s)
        elapsed_ms = round((timed() - t0) * 1000.0, 2)
        if resp.status_code >= 400:
            body = (resp.text or "")[:400]
            log_event(logger, logging.WARNING, "llm_call_status", status_code=resp.status_code, elapsed_ms=elapsed_ms, body=body)
            raise RuntimeError(f"LLM API error status={resp.status_code} body={body}")
        data = resp.json()

        text = None
        choices = data.get("choices") or []
        if isinstance(choices, list) and choices:
            msg = choices[0].get("message") or {}
            if isinstance(msg, dict):
                text = msg.get("content") or msg.get("text")
        if not text:
            raise RuntimeError("No content in LLM response")
        out = str(text)
        log_event(logger, logging.INFO, "llm_call_ok", elapsed_ms=elapsed_ms, out_chars=len(out))
        return out
