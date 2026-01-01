import json
import hashlib
import os
import re
import requests
import time
from pathlib import Path
from functools import lru_cache
from typing import Optional
import broadcast_assignments
import logging

from logging_setup import bind_log_context, log_event, setup_logging, timed
from agency_registry import get_agency_examples_key

try:
    from validator import validate as validate_extraction  # type: ignore
except Exception:
    validate_extraction = None  # type: ignore

setup_logging()
logger = logging.getLogger("extract_key_info")

# Reuse HTTP sessions for better throughput (keep-alive) when doing large backfills.
_LLM_SESSION = requests.Session()
_NOMINATIM_SESSION = requests.Session()

# No local model fallback: require a local LLM HTTP API (LM Studio / Mixtral).
# Configure the endpoint via the LLM_API_URL environment variable (e.g. http://127.0.0.1:7860/api/generate)

# Default to the Mixtral instruct model you installed in LM Studio
MODEL_NAME = "lfm2-8b-a1b"

# SYSTEM PROMPT
# When updating this system prompt, make sure to update message_examples/templates/verify extraction.txt too if necessary.
SYSTEM_PROMPT = f"""
You are an extractor that receives an unstructured tuition assignment post (English). You will be provided with examples of raw posts and the expected structured JSON output.
Extract the following keys and normalize values using these canonical lists.

Schema (output JSON):
{{
    "assignment_code": string or null,              # Alphanumeric code if present, else null
    "is_tuition_centre": boolean,                   # Whether tuition centre assignment
    "academic_tags_raw": string or null,            # Raw academic tags from post (e.g., "2026 P6 Science", "Sec 3 Express Maths", "Sec 4 G3 Maths")
    "subjects": [string],                           # Normalized list of subjects
    "level": [string] or null,                        # Canonical LEVELS
    "specific_student_level": [string] or null,       # Canonical SPECIFIC_LEVELS[level]
    "student_gender": [string] or null,             # Male / Female 
    "student_count": number or null,                # Number of students if mentioned
    "learning_mode": [string] or null,                # Online / Face-to-Face / Hybrid
    "address": [string] or null,                      # Do not include nearest MRT here (multiple locations allowed)
    "postal_code": [string] or null,                  # Multiple postal codes allowed (match addresses when applicable)
    "nearest_mrt": [string] or null,                  # Optional
    "frequency": string or null,                    # e.g., "1x per week"
    "duration": string or null,                     # e.g., "1.5 hours"
    "start_date": string or null,                   # Earliest start date mentioned
    "time_slots": {{                                # Normalized day → list of HH:MM-HH:MM ranges
        "monday": [string],
        "tuesday": [string],
        "wednesday": [string],
        "thursday": [string],
        "friday": [string],
        "saturday": [string],
        "sunday": [string]
    }} or null,
    "estimated_time_slots": {{                      # Normalized day → list of HH:MM-HH:MM ranges
        "monday": [string],
        "tuesday": [string],
        "wednesday": [string],
        "thursday": [string],
        "friday": [string],
        "saturday": [string],
        "sunday": [string]
    }} or null,
    "time_slots_note": string or null,              # Raw timeslot from post
    "hourly_rate": string or null,                  # Raw text from post
    "rate_min": number or null,
    "rate_max": number or null,
    "tutor_gender": string or null,                 # Preference if mentioned
    "tutor_type": [string] or null,                 # PT / FT / MOE / Graduate / Undergrad. Return all types explicitly mentioned, else null.
    "slot_details": [                               # Optional: multi-slot breakdown for tuition centre assignments
        {{
            "subject": string,
            "student_level": string,
            "day": string,
            "start_time": string,
            "end_time": string,
            "location": string
        }}
    ] or null,
    "additional_remarks": string or null,
}}


Normalization rules:
1. is_tuition_centre: Indicates whether the assignment is a tuition centre assignment.
   - If it is a tuition centre assignment or the post mentions multiple students at a centre, use true.
   - Else, use false.
2. Subjects: Map all synonyms to canonical names in SUBJECTS[level].
3. Levels: Map all synonyms to canonical LEVELS.
4. Specific student level: Must match SPECIFIC_LEVELS[level].
5. Time slots: Normalize to dictionary (day → list of HH:MM-HH:MM). 
   - Include all 7 days even if empty.
   - If the post mentions specific timing ranges (e.g., “3pm-5pm”), use that directly.
   - If the post only mentions a specific timing without a range (e.g., “3pm”) and there is no before/after wording, then use the mentioned time as start and add the duration to determine end time.
   - Only use this field for timings specifically mentioned in the post.
6. Estimated time slots: Normalize to dictionary (day → list of HH:MM-HH:MM). 
   - Include all 7 days even if empty.
   - Use this field to generate estimated time slots based on ambiguous timing mentions like "morning", "evening", "night", "weekdays", "weekends", "after 3pm" etc.
   - If the post mentions “after HH:MM” with no end time, extend the timeslot to 23:00.
   - If the post mentions “before HH:MM” with no start time, use 08:00 as the start.
   - Only use this field for estimated timings, not explicitly mentioned times.
   - "morning" = 08:00-12:00, "afternoon" = 12:00-17:00, "evening" = 16:00-21:00, "night" = 19:00-23:00, "weekdays" = Mon-Fri 08:00-23:00, "weekends" = Sat-Sun 08:00-23:00.
7. Rates: Extract min/max numeric values if parsable.
8. Frequency/Duration: Normalize to consistent strings.
9. Start date: Normalize to YYYY-MM-DD if possible, else raw text.
10. Always return JSON **only**, with keys in the order above. Stop immediately after last closing brace.
11. Treat each field independently (atomic extraction) to reduce hallucinations.
12. Do not guess fields; use null if missing.

LEVELS = [
    "Pre-School", "Primary", "Secondary", "IGCSE", "IB",
    "Junior College", "Diploma", "Degree", "Olympiads",
    "Independent Learner - Languages", "Independent Learner - Computing",
    "Independent Learner - Music", "Independent Learner - Others"
]

SPECIFIC_LEVELS = {{
    "Pre-School": ["Nursery", "Kindergarten 1", "Kindergarten 2"],
    "Primary": ["Primary 1", "Primary 2", "Primary 3", "Primary 4", "Primary 5", "Primary 6"],
    "Secondary": ["Secondary 1", "Secondary 2", "Secondary 3", "Secondary 4", "Secondary 5"],
    "IGCSE": ["Pre-IGCSE Grade 6", "Pre-IGCSE Grade 7", "Pre-IGCSE Grade 8", "IGCSE Grade 9", "IGCSE Grade 10"],
    "IB": ["IB MYP Grade 6", "IB MYP Grade 7", "IB MYP Grade 8", "IB MYP Grade 9", "IB MYP Grade 10", "IB DP Year 1", "IB DP Year 2"],
    "Junior College": ["JC 1", "JC 2", "JC 3", "Private Candidate"],
    "Diploma": ["Poly Year 1", "Poly Year 2", "Poly Year 3"],
    "Olympiads": ["Primary School Olympiad", "Olympiads Secondary", "Olympiads JC"]
}}

SUBJECTS = {{
    "Pre-School": [
        "English",
        "Chinese",
        "Maths",
        "Phonics",
        "Creative Writing",
        "Malay",
        "Tamil"
    ],
    "Primary": [
        "English",
        "Maths",
        "Science",
        "Chinese",
        "Higher Chinese",
        "Malay",
        "Higher Malay",
        "Tamil",
        "Higher Tamil",
        "Hindi",
        "Creative Writing",
        "Phonics",
        "Maths Olympiad",
        "Science Olympiad"
    ],
    "Secondary": [
        "English",
        "Chinese",
        "Higher Chinese",
        "Maths",
        "Science",
        "E Maths",
        "A Maths",
        "Physics",
        "Chemistry",
        "Biology",
        "Physics/Chem",
        "Bio/Physics",
        "Bio/Chem",
        "Geography",
        "History",
        "Literature",
        "Accounting (POA)",
        "Social Studies",
        "Geo/S.Studies",
        "Hist/S.Studies",
        "Malay",
        "Tamil",
        "Higher Malay",
        "Higher Tamil",
        "Hindi",
        "Creative Writing",
        "Music"
    ],

    "Junior College": [
        "General Paper",
        "Maths",
        "Physics",
        "Chemistry",
        "Biology",
        "Economics",
        "Accounting",
        "History",
        "Geography",
        "Literature",
        "Chinese",
        "Malay",
        "Tamil",
        "Chinese Studies",
        "Malay Studies",
        "Tamil Studies",
        "Knowledge & Inquiry",
        "Project Work",
        "Computing",
        "Art",
        "Theatre Studies & Drama",
        "Management of Business",
        "H3 Literature",
        "H3 Modern Physics",
        "H3 Chemistry",
        "H3 Proteomics",
        "H3 Maths",
        "H3 Geography",
        "H3 History",
        "H3 Economics",
        "Chinese Language and Literature",
        "Malay Language and Literature",
        "Tamil Language and Literature"
    ],

    "IB/IGCSE": [
        "English Language",
        "English Literature",
        "Chinese",
        "Mathematics",
        "Mathematical Studies",
        "Physics",
        "Chemistry",
        "Biology",
        "Business Management",
        "Economics",
        "Psychology",
        "Theory of Knowledge",
        "Extended Essay",
        "Theatre",
        "Environmental Systems",
        "Design Technology",
        "Geography",
        "History",
        "Malay",
        "Tamil",
        "Religious Knowledge",
        "Music",
        "Visual Arts",
        "Drama",
        "Art & Design",
        "IGTS"
    ],

    "Diploma": [
        "Business & Finance",
        "Computing & Technology",
        "Engineering & Applied Sciences",
        "Health & Life Sciences",
        "Arts, Humanities & Social Sciences"
    ],

    "Degree": [
        "Business & Finance",
        "Computing & Technology",
        "Engineering & Applied Sciences",
        "Health & Life Sciences",
        "Arts, Humanities & Social Sciences"
    ],

    "Olympiads": [
        "Primary School Math Olympiads",
        "Primary School Science Olympiads",
        "SMO (Junior)",
        "SJPO",
        "SJCHO",
        "SJBO",
        "SMO (Senior)",
        "SMO (Open)",
        "SPHO",
        "SCHO",
        "SBO",
        "APHO",
        "IPHO",
        "IOI",
        "NRC"
    ],

    "Independent Learner - Languages": [
        "Japanese",
        "Korean",
        "French",
        "German",
        "Spanish",
        "Russian",
        "Italian",
        "English",
        "Chinese",
        "Portuguese",
        "Arabic",
        "Vietnamese",
        "Thai",
        "Indonesian",
        "Tagalog",
        "Hindi",
        "Bengali"
    ],
    "Independent Learner - Computing": [
        "Python",
        "C++",
        "C#",
        "Java",
        "JavaScipt",
        "ASP",
        "PHP",
        "VB",
        "MSSQL",
        "Oracle",
        "Photoshop",
        "Illustrator",
        "Autocad",
        "GIS",
        "3D Design",
        "Flash",
        "Web Design",
        "Linux",
        "Macintosh",
        "Solaris",
        "Windows",
        "MS Office",
        "MySQL"
    ],
    "Independent Learner - Music": [
        "Music Theory",
        "Piano",
        "Guitar",
        "Drum",
        "Violin",
        "Flute",
        "Clarinet",
        "Trumpet",
        "Saxophone",
        "Dance",
        "Gu Zheng"
    ],
    "Independent Learner - Others": [
        "Others"
    ]
}}

Additional instructions:
- Treat each field **independently** (atomic extraction) to avoid cross-field hallucination.
- Use canonical forms wherever possible.
- Do not guess fields if the information is missing; use null.
- For ambiguous time slots or availability, use time_slots_note.
- Abbreviations to normalize:
  - Pri / P1..P6 -> Primary / Primary 1..6
  - Sec / S1..S5 -> Secondary / Secondary 1..5
  - JC / J1..J3 -> Junior College / JC 1..3
- Respond in a **single JSON object**.
"""

# -----------------------------
# System prompt overrides (A/B)
# -----------------------------

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def _prompt_sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


@lru_cache(maxsize=64)
def get_system_prompt_text() -> str:
    """
    Return the system prompt text used for extraction.

    Overrides (highest priority first):
    - `LLM_SYSTEM_PROMPT_TEXT` (inline)
    - `LLM_SYSTEM_PROMPT_FILE` (path to a prompt file; relative paths are relative to `TutorDexAggregator/`)
    - `LLM_SYSTEM_PROMPT_VARIANT` (loads `prompts/system_prompt_<variant>.txt` if it exists)

    Falls back to the hardcoded `SYSTEM_PROMPT`.
    """
    inline = (os.environ.get("LLM_SYSTEM_PROMPT_TEXT") or "").strip()
    if inline:
        return inline

    file_path = (os.environ.get("LLM_SYSTEM_PROMPT_FILE") or "").strip()
    if file_path:
        p = Path(file_path).expanduser()
        if not p.is_absolute():
            p = (Path(__file__).resolve().parent / p).resolve()
        return p.read_text(encoding="utf-8").strip()

    variant = (os.environ.get("LLM_SYSTEM_PROMPT_VARIANT") or "").strip()
    if variant:
        p = PROMPTS_DIR / f"system_prompt_{variant}.txt"
        if p.exists():
            return p.read_text(encoding="utf-8").strip()

    return SYSTEM_PROMPT.strip()


def get_system_prompt_meta() -> dict:
    """
    Metadata describing the current system prompt configuration.
    Intended to be persisted (e.g., in `telegram_extractions.meta`) for A/B comparisons.
    """
    inline = (os.environ.get("LLM_SYSTEM_PROMPT_TEXT") or "").strip()
    file_path = (os.environ.get("LLM_SYSTEM_PROMPT_FILE") or "").strip()
    variant = (os.environ.get("LLM_SYSTEM_PROMPT_VARIANT") or "").strip()

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
        except Exception:
            pass
    elif variant:
        meta["source"] = "env:LLM_SYSTEM_PROMPT_VARIANT"
        meta["variant"] = variant
        try:
            p = PROMPTS_DIR / f"system_prompt_{variant}.txt"
            meta["resolved_file"] = str(p)
            meta["missing"] = not p.exists()
        except Exception:
            pass
    else:
        meta["source"] = "code:SYSTEM_PROMPT"
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

    override = (os.environ.get("LLM_EXAMPLES_DIR") or "").strip()
    if override:
        p = Path(override).expanduser()
        if not p.is_absolute():
            p = (base_dir / p).resolve()
        return p

    variant = (os.environ.get("LLM_EXAMPLES_VARIANT") or "").strip()
    if variant:
        p = base_dir / "message_examples_variants" / variant
        if p.exists():
            return p

    return base_dir / "message_examples"


def get_examples_meta(chat: str) -> dict:
    """
    Metadata describing the examples context used for this chat (if enabled).
    """
    include = _truthy(os.environ.get("LLM_INCLUDE_EXAMPLES")) if os.environ.get("LLM_INCLUDE_EXAMPLES") is not None else False
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
            "variant": (os.environ.get("LLM_EXAMPLES_VARIANT") or "").strip() or None,
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
    "====================\n"
    "BEGIN TARGET MESSAGE\n"
    "====================\n"
    "You MUST extract facts ONLY from the TARGET MESSAGE below.\n"
    "The examples above are ONLY formatting guidance and MUST NOT be used as a source of facts.\n"
    "Do NOT copy values from examples.\n"
    "If a value is not explicitly present in the TARGET MESSAGE, output null/[] as required by the schema.\n"
    "\n"
    "TARGET MESSAGE:\n"
    "\"\"\"\n"
    "{message}\n"
    "\"\"\"\n"
    "\n"
    "OUTPUT JSON ONLY:\n"
    "====================\n"
    "END TARGET MESSAGE\n"
    "====================\n"
    "\n"
    "JSON:"
)

EXAMPLES_WRAPPER_HEADER = (
    "====================\n"
    "BEGIN EXAMPLES (FORMAT ONLY)\n"
    "====================\n"
    "The following are examples of (Raw -> JSON) for formatting reference ONLY.\n"
    "They are NOT the target message.\n"
)

EXAMPLES_WRAPPER_FOOTER = (
    "\n"
    "====================\n"
    "END EXAMPLES\n"
    "====================\n"
)


def build_prompt(message: str, chat: str) -> str:
    """
    Build the full user prompt by selecting an agency examples file based on `chat`.

    `chat` is expected to look like `t.me/<ChannelUsername>` (as produced by `read_assignments.py`).
    """
    include_examples = _truthy(os.environ.get("LLM_INCLUDE_EXAMPLES")) if os.environ.get("LLM_INCLUDE_EXAMPLES") is not None else False
    if include_examples:
        examples_key = get_agency_examples_key(chat) or None
        examples_text = get_examples_text(examples_key)
        wrapped_examples = (EXAMPLES_WRAPPER_HEADER + "\n" + examples_text.strip() + EXAMPLES_WRAPPER_FOOTER).strip()
        return (wrapped_examples + "\n\n" + PROMPT_FOOTER.format(message=message)).strip()

    return PROMPT_FOOTER.format(message=message)


def parse_rate(raw: str):
    # simple heuristic rate parser (improve as needed)
    import re
    m = re.findall(r"(\d+(?:[.,]\d+)?)(?:\s*(?:-|–|to)\s*(\d+(?:[.,]\d+)?))?", raw, flags=re.IGNORECASE)
    if not m:
        return None, None
    mn = float(m[0][0].replace(",", ""))
    mx = m[0][1]
    mx = float(mx.replace(",", "")) if mx else mn
    return mn, mx


def safe_parse_json(json_string):
    """
    Attempts to fix common JSON issues (like trailing commas) and parse it.
    """
    # Remove trailing commas before closing braces/brackets
    fixed_json = re.sub(r',\s*([}\]])', r'\1', json_string)

    try:
        parsed = json.loads(fixed_json)
        return parsed
    except json.JSONDecodeError as e:
        raise Exception(f"JSON parsing error: {e}") from e


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
    import os

    llm_api = os.environ.get("LLM_API_URL", "http://localhost:1234")
    model_name_env = os.environ.get("LLM_MODEL_NAME", model_name)
    timeout_s = int(os.environ.get("LLM_TIMEOUT_SECONDS") or "200")

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

        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("No JSON object found in model output")
        candidate = text[start:end+1].replace("\\_", "_")

        try:
            parsed = safe_parse_json(candidate)
        except Exception as e:
            log_event(logger, logging.WARNING, "llm_json_parse_failed", candidate_chars=len(candidate or ""))
            raise RuntimeError("Failed to parse JSON from model output") from e

        if validate_extraction and isinstance(parsed, dict):
            try:
                parsed = validate_extraction(parsed)
            except Exception as e:
                # Do not fail the pipeline due to validator bugs; continue with raw extraction.
                log_event(logger, logging.WARNING, "validator_failed", error=str(e))

        return parsed


def _nominatim_user_agent() -> str:
    return os.environ.get("NOMINATIM_USER_AGENT") or "TutorDex/1.0"


@lru_cache(maxsize=20000)
def _estimate_postal_from_cleaned_address(cleaned_address: str, timeout: float = 30.0) -> Optional[str]:
    if not cleaned_address:
        return None

    params = {
        "q": cleaned_address + ", Singapore",
        "format": "json",
        "countrycodes": "sg",
        "addressdetails": 1,
        "limit": 5,
    }
    url = "https://nominatim.openstreetmap.org/search"
    headers = {"User-Agent": _nominatim_user_agent()}
    q = params.get("q") or ""

    # Nominatim is rate-limited; retry gently on 429/503 with backoff.
    last_err: Optional[Exception] = None
    for attempt in range(3):
        try:
            log_event(logger, logging.INFO, "nominatim_lookup_start", q_chars=len(q), attempt=attempt + 1)
            start_ts = timed()
            resp = _NOMINATIM_SESSION.get(url, params=params, headers=headers, timeout=timeout)

            if resp.status_code in {429, 503}:
                retry_after = resp.headers.get("Retry-After")
                sleep_s = 2.0 * (attempt + 1)
                if retry_after:
                    try:
                        sleep_s = max(sleep_s, float(retry_after))
                    except Exception:
                        pass
                log_event(logger, logging.WARNING, "nominatim_throttled", status_code=resp.status_code, sleep_s=sleep_s)
                time.sleep(min(20.0, sleep_s))
                continue

            resp.raise_for_status()
            results = resp.json()
            log_event(
                logger,
                logging.INFO,
                "nominatim_lookup_ok",
                status_code=getattr(resp, "status_code", None),
                elapsed_ms=round((timed() - start_ts) * 1000.0, 2),
                results=len(results) if isinstance(results, list) else None,
            )

            for idx, r in enumerate(results if isinstance(results, list) else []):
                address_details = r.get("address", {}) if isinstance(r, dict) else {}
                postal = address_details.get("postcode") if isinstance(address_details, dict) else None
                log_event(logger, logging.DEBUG, "nominatim_result", idx=idx, has_postcode=bool(postal))
                if postal:
                    m = re.search(r"(\d{6})", str(postal))
                    if m:
                        return m.group(1)

                display_name = r.get("display_name", "") if isinstance(r, dict) else ""
                m = re.search(r"(\d{6})", str(display_name))
                if m:
                    return m.group(1)

            log_event(logger, logging.INFO, "nominatim_lookup_no_postcode", q_chars=len(q))
            return None
        except Exception as e:
            last_err = e
            log_event(logger, logging.WARNING, "nominatim_lookup_failed", q_chars=len(cleaned_address), error=str(e), attempt=attempt + 1)
            time.sleep(min(10.0, 1.0 * (attempt + 1)))

    if last_err:
        return None
    return None


def estimate_postal_from_address(address: object, timeout: float = 30.0) -> Optional[str]:
    """
    Use OpenStreetMap Nominatim API to estimate a postal code for a given address string.
    No API key required. Free service with usage limits.

    Returns the postal code string (6 digits) if found, otherwise None.
    """
    if str(os.environ.get("DISABLE_NOMINATIM", "")).strip().lower() in {"1", "true", "yes", "y"}:
        log_event(logger, logging.DEBUG, "nominatim_disabled")
        return None

    # Normalize address to a string early (LLM sometimes returns lists for string fields)
    address_text = ""
    try:
        if address is None:
            address_text = ""
        elif isinstance(address, (list, tuple)):
            parts = [str(x).strip() for x in address if x is not None and str(x).strip()]
            address_text = " ".join(parts)
        else:
            address_text = str(address).strip()
    except Exception:
        logger.debug("Failed to normalize address for postal estimation", exc_info=True)
        address_text = ""

    if not address_text:
        return None

    # Filter out the word "near" from the address
    cleaned_address = re.sub(r'\bnear\b', '', address_text, flags=re.IGNORECASE).strip()

    # First try heuristic extraction of 6-digit code from address
    m = re.search(r"\b(\d{6})\b", cleaned_address)
    if m:
        log_event(logger, logging.DEBUG, "postal_heuristic_hit", postal=m.group(1), address_chars=len(cleaned_address))
        return m.group(1)

    # Remove any bracketed text to improve geocoding
    cleaned_address = re.sub(r'[\[\(].*?[\]\)]', '', cleaned_address).strip()

    # If no postal code found in text, try Nominatim API
    return _estimate_postal_from_cleaned_address(cleaned_address, timeout=timeout)


def process_parsed_payload(payload: dict, do_send: bool = False) -> dict:
    """
    Enrich a payload (as produced by read_assignments) by ensuring postal codes.
    If parsed.postal_code is missing and address present, attempt to estimate it and
    write the result under parsed['postal_code_estimated'].

    If do_send is True, call broadcast_assignments.send_broadcast(payload) after enrichment.
    Returns the (possibly modified) payload.
    """
    parsed = payload.get('parsed') if isinstance(payload, dict) else None
    if not parsed:
        return payload

    # Back-compat: broadcaster/persistence may expect a "type" field.
    # Derive it from signals if present and type is missing.
    if isinstance(parsed, dict) and (parsed.get("type") is None or str(parsed.get("type")).strip() == ""):
        tc_sig = str(parsed.get("tuition_centre_signal") or "").strip()
        pv_sig = str(parsed.get("private_signal") or "").strip()
        if tc_sig:
            parsed["type"] = "Tuition Centre"
        elif pv_sig:
            parsed["type"] = "Private"

    cid = payload.get("cid") if isinstance(payload, dict) else None
    chat = payload.get("channel_link") if isinstance(payload, dict) else None
    message_id = payload.get("message_id") if isinstance(payload, dict) else None

    def _coerce_text(value) -> str:
        if value is None:
            return ""
        if isinstance(value, (list, tuple)):
            parts = [str(x).strip() for x in value if x is not None and str(x).strip()]
            return " ".join(parts).strip()
        return str(value).strip()

    def _coerce_text_list(value) -> list[str]:
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            return [str(x).strip() for x in value if x is not None and str(x).strip()]
        text = str(value).strip()
        return [text] if text else []

    def _extract_sg_postal_code(value) -> Optional[str]:
        text = _coerce_text(value)
        if not text:
            return None
        m = re.search(r"\b(\d{6})\b", text)
        return m.group(1) if m else None

    def _extract_sg_postal_codes(value) -> list[str]:
        codes: list[str] = []
        for item in _coerce_text_list(value):
            m = re.search(r"\b(\d{6})\b", item)
            if m:
                codes.append(m.group(1))
        # de-dup while preserving order
        seen = set()
        deduped: list[str] = []
        for c in codes:
            if c in seen:
                continue
            seen.add(c)
            deduped.append(c)
        return deduped

    def _extract_address_from_raw_text(raw_text: str) -> Optional[str]:
        if not raw_text:
            return None
        for line in str(raw_text).splitlines():
            ln = line.strip()
            if not ln:
                continue
            if ln.startswith("📍"):
                candidate = ln.lstrip("📍").strip()
                return candidate or None
            m = re.match(r"(?i)^(address|location)\s*[:：]\s*(.+)$", ln)
            if m:
                candidate = (m.group(2) or "").strip()
                return candidate or None
        return None

    def _log_assignment_json(stage: str) -> None:
        log_full = str(os.environ.get("LOG_ASSIGNMENT_JSON", "")).strip().lower() in {"1", "true", "yes", "y"}
        try:
            dumped = json.dumps(parsed, ensure_ascii=False)
        except Exception:
            dumped = str(parsed)
        log_event(
            logger,
            logging.INFO if log_full else logging.DEBUG,
            "assignment_json",
            stage=stage,
            cid=cid,
            chat=chat,
            message_id=message_id,
            parsed=dumped,
        )

    _log_assignment_json(stage="pre_enrich")

    # Normalize explicit postal_code(s) to 6-digit strings, or set to None.
    original_postal = parsed.get("postal_code")
    explicit_postals = _extract_sg_postal_codes(original_postal)
    if explicit_postals:
        # Preserve list vs scalar shape where possible (downstream code supports both).
        if isinstance(original_postal, (list, tuple)):
            parsed["postal_code"] = explicit_postals
        else:
            parsed["postal_code"] = explicit_postals[0]
    else:
        if _coerce_text(original_postal):
            log_event(
                logger,
                logging.WARNING,
                "invalid_postal_code_value",
                cid=cid,
                chat=chat,
                message_id=message_id,
                postal_code=str(original_postal)[:120],
            )
        parsed["postal_code"] = None

    # If postal_code is falsy, attempt estimation
    if not parsed.get('postal_code'):
        raw_text = payload.get("raw_text") if isinstance(payload, dict) else ""

        # Step between: try regex fill from raw text first (6-digit SG postal-like tokens).
        try:
            raw_postals = re.findall(r"\b(\d{6})\b", str(raw_text or ""))
        except Exception:
            raw_postals = []

        # de-dup while preserving order
        seen = set()
        raw_postals = [c for c in raw_postals if c and not (c in seen or seen.add(c))]

        if raw_postals:
            parsed["postal_code"] = raw_postals if len(raw_postals) > 1 else raw_postals[0]
            parsed["postal_code_estimated"] = None
            log_event(
                logger,
                logging.INFO,
                "postal_regex_fill_ok",
                cid=cid,
                chat=chat,
                message_id=message_id,
                count=len(raw_postals),
            )
        else:
            log_event(
                logger,
                logging.DEBUG,
                "postal_regex_fill_none",
                cid=cid,
                chat=chat,
                message_id=message_id,
            )

        # If regex fill succeeded, skip Nominatim estimation.
        if parsed.get("postal_code"):
            log_event(logger, logging.DEBUG, "postal_estimate_skipped", cid=cid, chat=chat, message_id=message_id, reason="postal_regex_filled")
        else:
            address_value = parsed.get("address")
            address_list = _coerce_text_list(address_value)
            if not address_list:
                raw_addr = _extract_address_from_raw_text(raw_text) or ""
                address_list = [raw_addr.strip()] if raw_addr.strip() else []

            if not address_list:
                parsed['postal_code_estimated'] = None
                log_event(logger, logging.INFO, "postal_estimate_skipped", cid=cid, chat=chat, message_id=message_id, reason="missing_address")
            else:
                estimated_codes: list[str] = []
                for idx, addr in enumerate(address_list, start=1):
                    try:
                        log_event(
                            logger,
                            logging.DEBUG,
                            "postal_estimate_start",
                            cid=cid,
                            chat=chat,
                            message_id=message_id,
                            addr_idx=idx,
                            addr_total=len(address_list),
                            address_chars=len(addr or ""),
                        )
                        code = estimate_postal_from_address(addr)
                    except Exception:
                        logger.debug("Postal estimate attempt failed", exc_info=True)
                        code = None
                    if code:
                        estimated_codes.append(code)

                # de-dup estimates while preserving order
                seen = set()
                estimated_codes = [c for c in estimated_codes if not (c in seen or seen.add(c))]

                if estimated_codes:
                    parsed['postal_code_estimated'] = estimated_codes if len(address_list) > 1 else estimated_codes[0]
                    log_event(logger, logging.INFO, "postal_estimate_ok", cid=cid, chat=chat, message_id=message_id, count=len(estimated_codes))
                else:
                    parsed['postal_code_estimated'] = None
                    log_event(logger, logging.INFO, "postal_estimate_none", cid=cid, chat=chat, message_id=message_id)
    else:
        log_event(logger, logging.DEBUG, "postal_estimate_skipped", cid=cid, chat=chat, message_id=message_id, reason="postal_present")

    try:
        log_event(
            logger,
            logging.INFO,
            "parsed_enrich_summary",
            cid=cid,
            chat=chat,
            message_id=message_id,
            has_address=bool(_coerce_text(parsed.get("address"))),
            has_postal=bool(parsed.get("postal_code")),
            has_postal_estimated=bool(parsed.get("postal_code_estimated")),
        )
    except Exception:
        logger.debug("Failed to emit parsed_enrich_summary", exc_info=True)

    _log_assignment_json(stage="post_enrich")

    # Optionally send via broadcaster
    if do_send:
        try:
            broadcast_assignments.send_broadcast(payload)
        except Exception:
            # do not raise — leave caller to handle
            logger.exception("broadcast_send_failed_during_enrich")

    return payload


def process_and_send(payload: dict) -> dict:
    """Convenience wrapper: enrich then send. Returns enrichment result dict."""
    enriched = process_parsed_payload(payload, do_send=False)
    # send synchronously
    try:
        broadcast_assignments.send_broadcast(enriched)
    except Exception:
        logger.exception("broadcast_send_failed_in_process_and_send")
    return enriched


if __name__ == "__main__":
    # Avoid UnicodeEncodeError on Windows consoles when printing sample text.
    try:
        import sys
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        logger.debug("stdout reconfigure failed", exc_info=True)
    sample = """
🔥 NEW Tuition Job! 🔥

▪️ Job Code: 253112W12
▪️ Job Details:
Info: P6 Science @ 30, Jalan Tanjong (nearest MRT station: Tanah Merah) on Wednesday 7.30pm-9.30pm ONLY [1 lesson/week, 2 hrs./lesson]

Requirement: An experienced FULL-TIME tutor or EX/CURRENT MOE Teacher for this St Stephen Primary School boy. Tutor to commit for at least 1 year. Earliest start date: 07-Jan-2026.

Rate: FULL-TIME $40-$55/hr.; EX/CURRENT MOE $75-$90/hr. Justify asking hourly rate with qualification, experience, and track record. Do not over quote!

Agency fee: FIRST 2 REGULAR LESSONS' WORTH
▪️ Tutor Types: Full-Time Tutor (Poly Grad), Ex-MOE, Full-Time Tutor (Uni Grad), Current MOE
▪️ Hashtags: #Primary_Science

💹 DOUBLE your chances of being selected by applying through the Website!

❤️ Forward this to your friends who might be interested in this assignment!

💎 Looking for Tutors or have a Tuition Job to post? With @sgTuitionsBot, press Start or send /start to begin!
"""

    chat = "t.me/FTassignments"

    print("=" * 60)
    print("STEP 0: Running compilation detection check...")
    print("=" * 60)

    # Import compilation detection from read_assignments
    try:
        from read_assignments import is_compilation
        is_comp, comp_details = is_compilation(sample)

        if is_comp:
            print("\n❌ COMPILATION DETECTED - Message would be SKIPPED")
            print("\nTriggered checks:")
            for detail in comp_details:
                print(f"  • {detail}")
            print("\n⚠️  This message will NOT be processed by the LLM.")
            print("=" * 60)
            import sys
            sys.exit(0)
        else:
            print("\n✅ PASSED - Not a compilation, proceeding to extraction...")
            print("=" * 60)
    except ImportError as e:
        print(f"\n⚠️  Could not import compilation check: {e}")
        print("Proceeding anyway...")
        print("=" * 60)

    print("\n" + "=" * 60)
    print("STEP 1: Extracting assignment info with LLM...")
    print("=" * 60)
    out = extract_assignment_with_model(sample, chat)
    print("\nExtracted data:")
    print(json.dumps(out, indent=2, ensure_ascii=False))

    # Check for validation errors
    if out.get('error') == 'validation_failed':
        print("\n❌ VALIDATION FAILED - Message would be SKIPPED")
        print(f"\nError: {out.get('error_detail')}")
        if out.get('validation_errors'):
            print("\nValidation errors:")
            for err in out['validation_errors']:
                print(f"  • {err.replace('_', ' ')}")
        print("\n⚠️  This message will NOT be processed further.")
        print("=" * 60)
        import sys
        sys.exit(0)
    else:
        print("\n✅ PASSED VALIDATION - Proceeding to enrichment...")

    print("\n" + "=" * 60)
    print("STEP 2: Creating payload and enriching with postal code...")
    print("=" * 60)

    # Create a payload structure similar to what read_assignments produces
    payload = {
        'raw_text': sample,
        'parsed': out,
        'channel_id': 'test',
        'message_id': 'test123'
    }

    # Run the full enrichment flow (includes postal code estimation)
    enriched = process_parsed_payload(payload, do_send=False)

    print("\nEnriched payload:")
    print(json.dumps(enriched, indent=2, ensure_ascii=False))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    parsed = enriched.get('parsed', {})
    # Print all top-level keys in the parsed dict, including nested dicts/lists

    def print_nested(d, prefix=""):
        if isinstance(d, dict):
            for k, v in d.items():
                if isinstance(v, dict):
                    print(f"{prefix}{k}:")
                    print_nested(v, prefix + "  ")
                elif isinstance(v, list):
                    print(f"{prefix}{k}: [")
                    for item in v:
                        if isinstance(item, dict):
                            print(f"{prefix}  - ")
                            print_nested(item, prefix + "    ")
                        else:
                            print(f"{prefix}  - {item}")
                    print(f"{prefix}]")
                else:
                    print(f"{prefix}{k}: {v}")
        else:
            print(f"{prefix}{d}")
    print_nested(parsed)
    # Also print postal_code_estimated if present in enriched
    if 'postal_code_estimated' in parsed:
        print(f"postal_code_estimated: {parsed['postal_code_estimated']}")
    print("=" * 60)
