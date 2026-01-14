"""
Compilation-message handling (LLM-assisted, fail-closed).

This module is responsible ONLY for:
- Calling the assignment-code extractor prompt for suspected compilation posts
- Treating LLM output as untrusted
- Verifying identifiers deterministically against the raw message
- Normalizing identifiers deterministically (only after verification)
- Splitting the raw message into per-assignment segments (based on verified identifiers)
"""

from __future__ import annotations

import json
import logging
import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

try:
    from logging_setup import bind_log_context, log_event, setup_logging, timed  # type: ignore
except Exception:  # pragma: no cover
    from TutorDexAggregator.logging_setup import bind_log_context, log_event, setup_logging, timed  # type: ignore

from shared.config import load_aggregator_config

setup_logging()
logger = logging.getLogger("compilation_message_handler")
_CFG = load_aggregator_config()


PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
ASSIGNMENT_CODE_EXTRACTOR_PROMPT_FILE = PROMPTS_DIR / "assignment_code_extractor_live.txt"


@lru_cache(maxsize=4)
def _prompt_template() -> str:
    return ASSIGNMENT_CODE_EXTRACTOR_PROMPT_FILE.read_text(encoding="utf-8")


def build_assignment_code_extractor_prompt(*, raw_message: str) -> str:
    template = _prompt_template()
    # The prompt file ends with "Message:"; append verbatim text below it.
    return (template.rstrip("\n") + "\n" + (raw_message or "")).rstrip() + "\n"


def _model_name() -> str:
    return str(_CFG.llm_model_name or "").strip() or "unknown"


def _llm_api_url() -> str:
    return str(_CFG.llm_api_url or "http://localhost:1234").strip().rstrip("/")


def _llm_timeout_seconds() -> int:
    try:
        return int(_CFG.llm_timeout_seconds)
    except Exception:
        return 200


def _safe_parse_json(json_string: str) -> Any:
    raw = json_string or ""
    try:
        from json_repair import repair_json  # type: ignore
    except Exception:
        return json.loads(raw)

    try:
        import inspect

        if "return_objects" in inspect.signature(repair_json).parameters:
            return repair_json(raw, return_objects=True)
    except Exception:
        pass

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


def _chat_completion(*, model_name: str, user_content: str, cid: Optional[str], channel: Optional[str]) -> str:
    url = f"{_llm_api_url()}/v1/chat/completions"
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": ""},
        {"role": "user", "content": (user_content or "").strip()},
    ]
    payload: Dict[str, Any] = {"model": model_name, "messages": messages, "temperature": 0.0}

    with bind_log_context(cid=str(cid) if cid else None, channel=channel or None, step="llm_assignment_code_extract"):
        log_event(logger, logging.INFO, "llm_call_start", model=model_name, url=url, user_chars=len(user_content or ""))
        t0 = timed()
        resp = requests.post(url, json=payload, timeout=_llm_timeout_seconds())
        elapsed_ms = round((timed() - t0) * 1000.0, 2)
        if resp.status_code >= 400:
            body = (resp.text or "")[:400]
            log_event(logger, logging.WARNING, "llm_call_status", status_code=resp.status_code, elapsed_ms=elapsed_ms, body=body)
            raise RuntimeError(f"LLM API error status={resp.status_code} body={body}")
        data = resp.json()
        text_out = None
        choices = data.get("choices") or []
        if isinstance(choices, list) and choices:
            msg = choices[0].get("message") or {}
            if isinstance(msg, dict):
                text_out = msg.get("content") or msg.get("text")
        if not text_out:
            raise RuntimeError("No content in LLM response")
        out = str(text_out)
        log_event(logger, logging.INFO, "llm_call_ok", elapsed_ms=elapsed_ms, out_chars=len(out))
        return out


def _read_mock_output() -> Optional[str]:
    p = str(_CFG.llm_assignment_code_extractor_mock_file or "").strip()
    if not p:
        return None
    path = Path(p).expanduser()
    if not path.is_absolute():
        path = (Path(__file__).resolve().parent / path).resolve()
    return path.read_text(encoding="utf-8")


def extract_assignment_identifiers_llm(
    *,
    raw_message: str,
    cid: Optional[str] = None,
    channel: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Call the LLM using ONLY `prompts/assignment_code_extractor_live.txt` (as user content).

    Returns an audit dict; caller must treat all output as untrusted.
    """
    prompt = build_assignment_code_extractor_prompt(raw_message=raw_message)

    mocked = _read_mock_output()
    if mocked is not None:
        llm_raw = mocked
        log_event(logger, logging.WARNING, "assignment_code_extract_mocked", file=str(_CFG.llm_assignment_code_extractor_mock_file or ""), out_chars=len(llm_raw or ""))
    else:
        llm_raw = _chat_completion(model_name=_model_name(), user_content=prompt, cid=cid, channel=channel)

    llm_raw_s = str(llm_raw or "")
    llm_raw_sha256 = hashlib.sha256(llm_raw_s.encode("utf-8")).hexdigest()
    raw_cap = 8000

    audit: Dict[str, Any] = {
        "ok": False,
        "llm_model": _model_name(),
        "llm_raw_output": llm_raw_s[:raw_cap],
        "llm_raw_truncated": len(llm_raw_s) > raw_cap,
        "llm_raw_sha256": llm_raw_sha256,
        "candidates": [],
        "parse_error": None,
    }

    try:
        obj = extract_json_object(llm_raw_s)
        raw_items = obj.get("assignment_codes")
        if not isinstance(raw_items, list):
            raise ValueError("Missing/invalid assignment_codes list")
        candidates: List[str] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            code = item.get("code")
            if not isinstance(code, str):
                continue
            if not code:
                continue
            candidates.append(code)
        # De-dup preserving order (verbatim; no stripping).
        seen = set()
        deduped: List[str] = []
        for c in candidates:
            if c in seen:
                continue
            seen.add(c)
            deduped.append(c)
        audit["ok"] = True
        audit["candidates"] = deduped
        return audit
    except Exception as e:
        audit["parse_error"] = str(e)
        return audit


def _is_boundary_alnum(ch: str) -> bool:
    # Treat only ASCII alnum as "token characters" for boundary checks.
    # This keeps boundaries conservative while avoiding false drops for punctuation-wrapped ids.
    return bool(ch) and (("0" <= ch <= "9") or ("A" <= ch <= "Z") or ("a" <= ch <= "z"))


def _find_verified_occurrence(text: str, token: str, *, start_at: int = 0) -> Optional[int]:
    """
    Find a token occurrence in `text` that satisfies boundary checks (when applicable).
    Returns the start index or None.
    """
    if not text or not token:
        return None
    i = max(0, int(start_at))
    while True:
        pos = text.find(token, i)
        if pos == -1:
            return None
        end = pos + len(token)
        before = text[pos - 1] if pos > 0 else ""
        after = text[end] if end < len(text) else ""

        first = token[0]
        last = token[-1]
        if _is_boundary_alnum(first) and pos > 0 and _is_boundary_alnum(before):
            i = pos + 1
            continue
        if _is_boundary_alnum(last) and end < len(text) and _is_boundary_alnum(after):
            i = pos + 1
            continue
        return pos


def verify_identifiers(
    *,
    raw_message: str,
    candidates: List[str],
) -> Dict[str, Any]:
    """
    Deterministically verify candidates against the raw message (verbatim match + boundary checks).

    Never normalizes candidates here.
    """
    verified: List[str] = []
    dropped: List[Dict[str, Any]] = []
    seen = set()

    for c in candidates or []:
        if not isinstance(c, str) or not c:
            dropped.append({"code": c, "reason": "non_string_or_empty"})
            continue
        if c in seen:
            continue
        seen.add(c)

        pos = _find_verified_occurrence(raw_message, c, start_at=0)
        if pos is None:
            dropped.append({"code": c, "reason": "not_verbatim_in_message"})
            continue
        verified.append(c)

    return {"verified": verified, "dropped": dropped}


def normalize_identifier(verbatim: str) -> str:
    """
    Deterministic normalization for identifiers (ONLY safe transforms).

    - Strips surrounding whitespace
    - Strips one layer of surrounding [], (), {} if they wrap the entire string
    - If a ':' exists, keeps the substring after the last ':' (common 'Code: 1234' forms)
    """
    s = str(verbatim or "").strip()
    if not s:
        return s

    # Strip one layer of wrapping brackets (common formats like "[Job 7782]").
    if (s.startswith("[") and s.endswith("]")) or (s.startswith("(") and s.endswith(")")) or (s.startswith("{") and s.endswith("}")):
        inner = s[1:-1].strip()
        if inner:
            s = inner

    if ":" in s:
        tail = s.rsplit(":", 1)[-1].strip()
        if tail:
            s = tail
    return s


@dataclass(frozen=True)
class VerifiedIdentifier:
    verbatim: str
    normalized: str
    pos: int
    line_start: int


def order_verified_identifiers(*, raw_message: str, verified: List[str]) -> List[VerifiedIdentifier]:
    items: List[VerifiedIdentifier] = []
    for v in verified or []:
        pos = _find_verified_occurrence(raw_message, v, start_at=0)
        if pos is None:
            continue
        line_start = raw_message.rfind("\n", 0, pos)
        line_start = 0 if line_start == -1 else line_start + 1
        items.append(
            VerifiedIdentifier(
                verbatim=v,
                normalized=normalize_identifier(v),
                pos=pos,
                line_start=line_start,
            )
        )

    items.sort(key=lambda x: x.pos)
    return items


def split_compilation_message(
    *,
    raw_message: str,
    identifiers: List[VerifiedIdentifier],
) -> List[Dict[str, Any]]:
    """
    Split a compilation post into per-assignment segments using verified identifier positions.
    """
    if not raw_message or not identifiers:
        return []

    # Deduplicate by line_start to avoid accidental overlaps.
    ordered: List[VerifiedIdentifier] = []
    seen_line_starts = set()
    for it in identifiers:
        if it.line_start in seen_line_starts:
            continue
        seen_line_starts.add(it.line_start)
        ordered.append(it)

    segments: List[Dict[str, Any]] = []
    for idx, it in enumerate(ordered):
        start = it.line_start
        end = ordered[idx + 1].line_start if idx + 1 < len(ordered) else len(raw_message)
        seg = raw_message[start:end].strip()
        if not seg:
            continue
        segments.append(
            {
                "index": idx,
                "identifier_verbatim": it.verbatim,
                "identifier_normalized": it.normalized or it.verbatim,
                "text": seg,
                "chars": len(seg),
            }
        )
    return segments


def confirm_compilation_identifiers(
    *,
    raw_message: str,
    cid: Optional[str] = None,
    channel: Optional[str] = None,
    min_verified: int = 2,
) -> Dict[str, Any]:
    """
    End-to-end helper:
    - LLM extraction using the code-extractor prompt
    - Deterministic verification
    - Confirmation when >= `min_verified` survive
    """
    llm_audit = extract_assignment_identifiers_llm(raw_message=raw_message, cid=cid, channel=channel)
    verify = verify_identifiers(raw_message=raw_message, candidates=list(llm_audit.get("candidates") or []))
    verified = list(verify.get("verified") or [])
    dropped = list(verify.get("dropped") or [])
    ordered = order_verified_identifiers(raw_message=raw_message, verified=verified)
    confirmed = len(verified) >= int(min_verified)
    return {
        "ok": bool(llm_audit.get("ok")),
        "confirmed": confirmed,
        "llm_model": llm_audit.get("llm_model"),
        "llm_raw_output": llm_audit.get("llm_raw_output"),
        "candidates": llm_audit.get("candidates") or [],
        "parse_error": llm_audit.get("parse_error"),
        "verified": verified,
        "dropped": dropped,
        "ordered": [it.__dict__ for it in ordered],
    }
