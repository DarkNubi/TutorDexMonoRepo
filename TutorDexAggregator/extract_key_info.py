import json
import hashlib
import requests
from pathlib import Path
from functools import lru_cache
from typing import Optional
import logging

from logging_setup import bind_log_context, log_event, setup_logging, timed
from agency_registry import get_agency_examples_key
from shared.config import load_aggregator_config
from shared.observability.exception_handler import swallow_exception

setup_logging()
logger = logging.getLogger("extract_key_info")
_CFG = load_aggregator_config()

# Reuse HTTP sessions for better throughput (keep-alive) when doing large backfills.
_LLM_SESSION = requests.Session()

# No local model fallback: require a local LLM HTTP API (LM Studio / Mixtral).
# Configure the endpoint via the LLM_API_URL environment variable (e.g. http://127.0.0.1:7860/api/generate)

# Default to the Mixtral instruct model you installed in LM Studio
MODEL_NAME = "lfm2-8b-a1b"

# -----------------------------
# System prompt overrides (A/B)
# -----------------------------

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
DEFAULT_SYSTEM_PROMPT_FILE = PROMPTS_DIR / "system_prompt_live.txt"


def _prompt_sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


@lru_cache(maxsize=64)
def get_system_prompt_text() -> str:
    """
    Return the system prompt text used for extraction.

    Overrides (highest priority first):
    - `LLM_SYSTEM_PROMPT_TEXT` (inline)
    - `LLM_SYSTEM_PROMPT_FILE` (path to a prompt file; relative paths are relative to `TutorDexAggregator/`)

    Falls back to `prompts/system_prompt_live.txt`.
    """
    inline = str(_CFG.llm_system_prompt_text or "").strip()
    if inline:
        return inline

    file_path = str(_CFG.llm_system_prompt_file or "").strip()
    if file_path:
        p = Path(file_path).expanduser()
        if not p.is_absolute():
            p = (Path(__file__).resolve().parent / p).resolve()
        return p.read_text(encoding="utf-8").strip()

    if DEFAULT_SYSTEM_PROMPT_FILE.exists():
        return DEFAULT_SYSTEM_PROMPT_FILE.read_text(encoding="utf-8").strip()

    raise FileNotFoundError(f"Missing default system prompt file: {DEFAULT_SYSTEM_PROMPT_FILE}")


def get_system_prompt_meta() -> dict:
    """
    Metadata describing the current system prompt configuration.
    Intended to be persisted (e.g., in `telegram_extractions.meta`) for A/B comparisons.
    """
    inline = str(_CFG.llm_system_prompt_text or "").strip()
    file_path = str(_CFG.llm_system_prompt_file or "").strip()

    prompt_text = get_system_prompt_text()
    meta = {
        "sha256": _prompt_sha256(prompt_text),
        "chars": len(prompt_text),
    }
    if inline:
        meta["source"] = "env:LLM_SYSTEM_PROMPT_TEXT"
    elif file_path:
        meta["source"] = "env:LLM_SYSTEM_PROMPT_FILE"
        meta["file"] = file_path
        try:
            p = Path(file_path).expanduser()
            if not p.is_absolute():
                p = (Path(__file__).resolve().parent / p).resolve()
            meta["resolved_file"] = str(p)
            meta["missing"] = not p.exists()
        except Exception as e:
            swallow_exception(e, context="metadata_file_resolution", extra={"module": __name__})
    else:
        meta["source"] = "file:prompts/system_prompt_live.txt"
        meta["resolved_file"] = str(DEFAULT_SYSTEM_PROMPT_FILE)
        meta["missing"] = not DEFAULT_SYSTEM_PROMPT_FILE.exists()
    return meta


def _truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _text_sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def get_examples_dir() -> Path:
    """
    Determine which examples directory to use.

    - `LLM_EXAMPLES_DIR`: absolute or relative path (relative to `TutorDexAggregator/`)
    - `LLM_EXAMPLES_VARIANT`: uses `message_examples_variants/<variant>/` if it exists
    - default: `message_examples/`
    """
    base_dir = Path(__file__).resolve().parent

    override = str(_CFG.llm_examples_dir or "").strip()
    if override:
        p = Path(override).expanduser()
        if not p.is_absolute():
            p = (base_dir / p).resolve()
        return p

    variant = str(_CFG.llm_examples_variant or "").strip()
    if variant:
        p = base_dir / "message_examples_variants" / variant
        if p.exists():
            return p

    return base_dir / "message_examples"


def get_examples_meta(chat: str) -> dict:
    """
    Metadata describing the examples context used for this chat (if enabled).
    """
    include = bool(_CFG.llm_include_examples)
    meta = {"enabled": bool(include)}
    if not include:
        return meta

    examples_dir = get_examples_dir()
    agency_key = get_agency_examples_key(chat) or None
    chosen = (examples_dir / f"{agency_key}.txt") if agency_key else (examples_dir / "general.txt")
    if not chosen.exists():
        chosen = examples_dir / "general.txt"

    try:
        text = chosen.read_text(encoding="utf-8")
    except Exception:
        text = ""

    meta.update(
        {
            "dir": str(examples_dir),
            "variant": str(_CFG.llm_examples_variant or "").strip() or None,
            "file": str(chosen),
            "sha256": _text_sha256(text),
            "chars": len(text),
            "agency_key": agency_key,
        }
    )
    return meta


# Message examples are stored as plain text files for easy editing.
# Default folder layout: TutorDexAggregator/message_examples/{agency}.txt
# Optional A/B layout: TutorDexAggregator/message_examples_variants/<variant>/{agency}.txt
DEFAULT_EXAMPLES_FILE = Path(__file__).resolve().parent / "message_examples" / "general.txt"


@lru_cache(maxsize=None)
def _read_examples_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def get_examples_text(agency: Optional[str]) -> str:
    """
    Load prompt examples from `message_examples/`.

    - Uses `<agency>.txt` when provided (agency name, not chat id)
    - Falls back to `general.txt`
    - Files are cached in-process via `lru_cache`
    """
    examples_dir = get_examples_dir()
    candidates = []
    if agency:
        candidates.append(examples_dir / f"{agency}.txt")
    candidates.append(examples_dir / "general.txt")

    for candidate in candidates:
        try:
            return _read_examples_file(candidate)
        except FileNotFoundError:
            logger.warning(f"examples_file_missing path={candidate}")
            continue

    raise FileNotFoundError(
        f"No examples files found. Tried: {', '.join(str(p) for p in candidates)}"
    )


PROMPT_FOOTER = (
    "\n\n"
    "You MUST extract facts ONLY from the TARGET MESSAGE below.\n"
    "The examples above are ONLY formatting guidance and MUST NOT be used as a source of facts.\n"
    "Do NOT copy values from examples.\n"
    "If a value is not explicitly present in the TARGET MESSAGE, output null/[] as required by the schema.\n"
    "────────────────────────────────────────\n"
    "BEGIN TARGET MESSAGE\n"
    "────────────────────────────────────────\n"
    "\"\"\"\n"
    "{message}\n"
    "\"\"\"\n"
    "────────────────────────────────────────\n"
    "END TARGET MESSAGE\n"
    "────────────────────────────────────────\n"
)

EXAMPLES_WRAPPER_HEADER = (
    "The following are examples of (Raw -> JSON) for formatting reference ONLY.\n"
    "They are NOT the target message.\n"
    "────────────────────────────────────────\n"
    "BEGIN EXAMPLES\n"
    "────────────────────────────────────────\n"

)

EXAMPLES_WRAPPER_FOOTER = (
    "\n"
    "────────────────────────────────────────\n"
    "END EXAMPLES\n"
    "────────────────────────────────────────\n"
)


def build_prompt(message: str, chat: str) -> str:
    """
    Build the full user prompt by selecting an agency examples file based on `chat`.

    `chat` is expected to look like `t.me/<ChannelUsername>`.
    """
    include_examples = bool(_CFG.llm_include_examples)
    if include_examples:
        examples_key = get_agency_examples_key(chat) or None
        examples_text = get_examples_text(examples_key)
        wrapped_examples = (EXAMPLES_WRAPPER_HEADER + "\n" + examples_text.strip() + EXAMPLES_WRAPPER_FOOTER).strip()
        return (wrapped_examples + "\n\n" + PROMPT_FOOTER.format(message=message)).strip()

    return PROMPT_FOOTER.format(message=message)


def safe_parse_json(json_string):
    """
    Parse JSON with a fast-path for valid JSON, and a fallback to `json-repair` for common model errors.
    """
    if json_string is None:
        raise Exception("JSON parsing error: empty input")

    def _strip_code_fences(s: str) -> str:
        s = str(s).strip()
        if s.startswith("```"):
            lines = s.splitlines()
            if lines:
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            s = "\n".join(lines).strip()
        return s

    raw = _strip_code_fences(json_string)

    # Fast path: valid JSON should not require `json-repair` to be installed.
    try:
        return json.loads(raw)
    except Exception as e:
        swallow_exception(
            e,
            context="json_parse_initial",
            extra={"raw_preview": str(raw)[:100], "module": __name__},
            level=logging.DEBUG,
        )

    try:
        from json_repair import repair_json  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "json-repair is required but not installed; run `pip install -r TutorDexAggregator/requirements.txt`"
        ) from e

    # Some versions support `return_objects=True`; use it if available.
    try:
        import inspect

        if "return_objects" in inspect.signature(repair_json).parameters:
            return repair_json(raw, return_objects=True)
    except Exception as e:
        swallow_exception(
            e,
            context="json_repair_advanced_sig",
            extra={"raw_preview": str(raw)[:100], "module": __name__},
            level=logging.DEBUG,
        )

    repaired = repair_json(raw)
    if isinstance(repaired, (dict, list)):
        return repaired
    if isinstance(repaired, str) and repaired.strip():
        return json.loads(repaired)
    raise Exception("JSON parsing error: json-repair produced empty output")


def extract_first_json_object(text: str) -> str:
    """
    Extract the first JSON object from a string by scanning for a brace-balanced `{...}`.

    This is more robust than `text.find('{')` + `text.rfind('}')` because the *last* `}`
    in the text might belong to a nested object (e.g. `rate`) if the model forgets to emit
    the final root `}` or if the remainder of fields contains no braces.
    """
    if text is None:
        raise ValueError("No text to extract JSON from")

    s = str(text)
    start = s.find("{")
    if start == -1:
        raise ValueError("No '{' found in model output")

    in_string = False
    escape = False
    depth = 0
    end: Optional[int] = None

    for i in range(start, len(s)):
        ch = s[i]

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break

    if end is not None:
        return s[start: end + 1]

    # No matching root `}` found → fall back to "best effort":
    # take from the first `{` to the end and append the missing `}` braces.
    tail = s[start:].rstrip()
    if depth > 0:
        tail = tail + ("}" * depth)
    return tail


def extract_assignment_with_model(message: str, chat: str = "", model_name: str = MODEL_NAME, max_tokens=2048, temp=0.0, cid: Optional[str] = None):
    """
    Generate extraction JSON by calling LM Studio/Mixtral using chat format
    with proper system + user messages.

    Args:
        message: The raw message text to extract from
        chat: The channel/chat identifier (e.g., "t.me/channelname") to select appropriate examples
        model_name: The LLM model to use
        max_tokens: Maximum tokens for response
        temp: Temperature for generation
    """

    llm_api = str(_CFG.llm_api_url or "http://localhost:1234")
    model_name_env = str(_CFG.llm_model_name or model_name)
    timeout_s = int(_CFG.llm_timeout_seconds or 200)

    system_prompt = get_system_prompt_text().strip()
    prompt_with_examples = build_prompt(message, chat=chat)

    with bind_log_context(cid=str(cid) if cid else None, channel=chat or None, step="llm_extract"):
        log_event(
            logger,
            logging.INFO,
            "llm_extract_start",
            chat=chat or None,
            model=model_name_env,
            prompt_chars=len(prompt_with_examples or ""),
        )

        messages = [
            {
                "role": "system",
                "content": (
                    system_prompt +
                    "\n\nFollow the schema exactly. Output JSON only.\n"
                )
            },
            {
                "role": "user",
                "content": prompt_with_examples.strip()
            }
        ]

        payload = {
            "model": model_name_env,
            "messages": messages,
            "temperature": float(temp),
            "max_tokens": int(max_tokens),
        }

        mock_path = str(_CFG.llm_mock_output_file or "").strip()
        if mock_path:
            p = Path(mock_path).expanduser()
            if not p.is_absolute():
                p = (Path(__file__).resolve().parent / p).resolve()
            text = p.read_text(encoding="utf-8")
            log_event(logger, logging.WARNING, "llm_extract_mocked", file=str(p), chars=len(text))
            data = {"_mocked": True}
        else:
            url = f"{llm_api.rstrip('/')}/v1/chat/completions"
            try:
                t0 = timed()
                r = _LLM_SESSION.post(url, json=payload, timeout=timeout_s)
                r.raise_for_status()
                data = r.json()
                log_event(
                    logger,
                    logging.INFO,
                    "llm_extract_ok",
                    status_code=getattr(r, "status_code", None),
                    elapsed_ms=round((timed() - t0) * 1000.0, 2),
                )
            except Exception as e:
                logger.exception("llm_extract_failed error=%s", e)
                raise RuntimeError(f"LLM API call failed: {e}")

            text = None
            try:
                choices = data.get("choices", [])
                if choices:
                    msg = choices[0].get("message", {})
                    text = msg.get("content") or msg.get("text")
                if not text and data.get("outputs"):
                    out = data["outputs"]
                    if isinstance(out, list) and len(out) > 0 and "content" in out[0]:
                        parts = out[0]["content"]
                        if isinstance(parts, list) and len(parts) > 0:
                            text = "".join([c.get("text", "") for c in parts if isinstance(c, dict)])
                if not text:
                    raise ValueError("No valid text found in LLM response")
            except Exception as e:
                raise RuntimeError(f"Failed to parse LLM response: {e}")

        text = text.strip().strip("```")
        candidate = extract_first_json_object(text).replace("\\_", "_")

        try:
            parsed = safe_parse_json(candidate)
        except Exception as e:
            # Include error message to avoid losing the useful snippet from safe_parse_json.
            log_event(
                logger,
                logging.WARNING,
                "llm_json_parse_failed",
                candidate_chars=len(candidate or ""),
                error=str(e),
            )
            raise RuntimeError(f"Failed to parse JSON from model output: {e}") from e

        # NOTE: Legacy `validator.py` post-processor removed. Hardening happens in:
        # - `hard_validator.py` (null/drop invariants)
        # - deterministic extractors (e.g., `extractors/time_availability.py`)

        return parsed


if __name__ == "__main__":
    # Avoid UnicodeEncodeError on Windows consoles when printing sample text.
    try:
        import sys
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        logger.debug("stdout reconfigure failed", exc_info=True)
    sample = """
Code ID: 0101pn
(Female Full-Time Tutor)
Subject: 2026 P6 Math
Address: 196B Boon Lay Drive (S)642196
Frequency: 1.5 Hr, 1x A Week
Rate: $40-55/Hr

- Available on: Sat 9am
- Start: 17 Jan
- Face-to-Face Lessons
------------------------------------
To apply: https://www.singaporetuitionteachers.com/adm/tutor/
Any bugs/questions, WhatsApp 9695 3522
    """

    chat = "t.me/TuitionAssignmentsSG"

    print("\n" + "=" * 60)
    print("PROMPT CONTEXT")
    print("=" * 60)
    try:
        meta = get_examples_meta(chat)
        if meta.get("enabled"):
            print(
                "Examples: enabled=True "
                f"file={meta.get('file')} "
                f"agency_key={meta.get('agency_key')} "
                f"variant={meta.get('variant')}"
            )
        else:
            print("Examples: enabled=False (set `LLM_INCLUDE_EXAMPLES=1` to enable few-shot)")
    except Exception as e:
        print(f"Examples: failed to resolve ({e})")
    print("=" * 60)

    print("\n" + "=" * 60)
    print("LLM OUTPUT (display fields only)")
    print("=" * 60)
    out = extract_assignment_with_model(sample, chat)
    print(json.dumps(out, indent=2, ensure_ascii=False))

    print("\n" + "=" * 60)
    print("NOTE")
    print("=" * 60)
    print("For the full hardened pipeline (normalize + deterministic time + hard_validate + signals), run:")
    print("  python3 utilities/run_sample_pipeline.py --file utilities/sample_assignment_post.sample.txt --print-json")
