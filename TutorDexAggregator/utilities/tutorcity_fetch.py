"""
Fetch TutorCity assignments API (no LLM) and persist/broadcast/DM via existing pipeline.

Usage:
  python utilities/tutorcity_fetch.py --limit 50

Environment variables:
  TUTORCITY_API_URL (default: https://tutorcity.sg/api/tuition-assignments/)
  TUTORCITY_LIMIT (default: 50)
  TUTORCITY_TIMEOUT_SECONDS (default: 30)
  (No source label env var; source is always "TutorCity")

This script:
  - calls the API once
  - maps rows into the hardened v2 `canonical_json` display schema
  - computes deterministic time availability + signals (meta)
  - persists via `supabase_persist` (which materializes `signals_*` columns for the website/backend)
"""

import argparse
import logging
import sys
from typing import Any, Dict, List, Optional

import requests

from pathlib import Path

from shared.config import load_aggregator_config

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from logging_setup import bind_log_context, log_event, setup_logging
from supabase_persist import SupabaseConfig, load_config_from_env, persist_assignment_to_supabase
from normalize import normalize_text
from extractors.time_availability import extract_time_availability
from signals_builder import build_signals

try:
    from dm_assignments import send_dms
except Exception:
    send_dms = None  # type: ignore

try:
    import broadcast_assignments
except Exception:
    broadcast_assignments = None  # type: ignore


setup_logging()
logger = logging.getLogger("tutorcity_fetch")

DEFAULT_URL = "https://tutorcity.sg/api/tuition-assignments/"

# NOTE: TutorCity returns `subjects` + `level` as IDs (strings). `year` is a direct integer-like string.
# We map IDs into labels to build `academic_display_text` and to store a readable `meta.source_mapped`.
TUTORCITY_MAPPING_VERSION = "2026-01-03_v1"

TUTORCITY_SUBJECT_ID_MAP: Dict[str, str] = {
    # --- Early / Primary (first select) ---
    "1": "English",
    "2": "Chinese",
    "3": "Malay",
    "4": "Tamil",
    "5": "Maths",
    "6": "Creative Writing",
    "7": "Phonics",
    # --- Primary (second select) ---
    "8": "English",
    "9": "Chinese",
    "10": "Malay",
    "11": "Tamil",
    "12": "Maths",
    "13": "Science",
    "14": "Creative Writing",
    "15": "Phonics",
    "16": "Higher Chinese",
    "17": "Higher Malay",
    "18": "Higher Tamil",
    "19": "Art",
    "171": "Hindi",
    # --- Secondary ---
    "20": "English",
    "21": "Chinese",
    "22": "Malay",
    "23": "Tamil",
    "24": "Lower Secondary Maths",
    "25": "Lower Secondary Science",
    "26": "E Maths",
    "27": "A Maths",
    "28": "Physics",
    "29": "Chemistry",
    "30": "Biology",
    "31": "Physics / Chemistry",
    "32": "Biology / Physics",
    "33": "Biology / Chemistry",
    "34": "Geography",
    "35": "History",
    "36": "Literature",
    "37": "Accounting",
    "38": "Social Studies",
    "39": "Geography / Social Studies",
    "40": "History / Social Studies",
    "41": "Higher Chinese",
    "42": "Higher Malay",
    "43": "Higher Tamil",
    "204": "Hindi",
    "205": "Design & Technology",
    "206": "Music",
    "207": "Food & Nutrition",
    "208": "Art",
    # --- JC / A Levels ---
    "44": "General Paper",
    "45": "AO Chinese",
    "46": "AO Malay",
    "47": "AO Tamil",
    "48": "Maths",
    "49": "Physics",
    "50": "Chemistry",
    "51": "Biology",
    "52": "Economics",
    "53": "Accounting",
    "54": "History",
    "55": "Geography",
    "56": "Literature",
    "57": "Chinese Studies",
    "58": "Malay Studies",
    "59": "Tamil Studies",
    "213": "Knowledge & Inquiry",
    "214": "Project Work",
    "215": "Computing",
    "216": "Art",
    "217": "Theatre Studies & Drama",
    "218": "Management of Business",
    "219": "H3 Literature",
    "220": "H3 Modern Physics",
    "221": "H3 Pharmaceutical Chemistry",
    "222": "H3 Proteomics",
    "223": "H3 Maths",
    "224": "H3 Geography",
    "225": "H3 History",
    "226": "H3 Economics",
    "227": "H3 Chinese",
    "228": "H3 Malay",
    "229": "H3 Tamil",
    # --- IB ---
    "60": "English Language",
    "61": "English Literature",
    "62": "Chinese",
    "63": "Malay",
    "64": "Tamil",
    "65": "Mathematics",
    "66": "Mathematical Studies",
    "67": "Physics",
    "68": "Chemistry",
    "69": "Biology",
    "70": "Business & Management",
    "71": "Economics",
    "72": "Extended Essay",
    "73": "Theatre",
    "74": "Environmental Systems",
    "75": "Design Technology",
    "76": "Geography",
    "77": "History",
    "78": "Religious Knowledge",
    "79": "Music",
    "80": "Visual Arts",
    "81": "Theory of Knowledge",
    "82": "Drama",
    "83": "Art & Design",
    "230": "IGTS",
    "231": "Psychology",
    # --- University ---
    "85": "Business Administration",
    "86": "Marketing",
    "87": "Mass Communication",
    "88": "Human Resource",
    "89": "Finance",
    "90": "Financial Engineering",
    "91": "Accounting",
    "92": "Mathematics",
    "93": "Applied Mathematics",
    "94": "Statistics",
    "95": "Economics",
    "96": "Law",
    "97": "Architecture",
    "98": "Real Estate",
    "99": "History",
    "100": "Geography",
    "101": "Sociology",
    "102": "Literature",
    "103": "Psychology",
    "104": "Medicine",
    "105": "Biological Science",
    "106": "Electrical Engineering",
    "107": "Chemical Engineering",
    "108": "Mechanical Engineering",
    "109": "Pharmacy",
    "110": "Physics",
    "111": "Chemistry",
    "112": "Biology",
    "113": "Bioengineering",
    "114": "Applied Chemistry",
    "115": "Life Sciences",
    "116": "Communications & New Media",
    "117": "E-Commerce",
    "118": "Computer Science",
    "119": "Information Technology",
    # --- Music / Performing Arts ---
    "120": "Music Theory",
    "121": "Piano",
    "122": "Guitar",
    "123": "Drums",
    "124": "Violin",
    "125": "Dance",
    "126": "Flute",
    "127": "Clarinet",
    "253": "Test1",
    # --- Foreign Languages ---
    "128": "English",
    "129": "Chinese",
    "130": "French",
    "131": "German",
    "132": "Spanish",
    "133": "Russian",
    "134": "Italian",
    "135": "Portuguese",
    "136": "Arabic",
    "137": "Japanese",
    "138": "Korean",
    "139": "Vietnamese",
    "140": "Thai",
    "141": "Indonesian",
    "142": "Tagalog",
    "143": "Hindi",
    "144": "Bengali",
    # --- IT / Software / Design ---
    "145": "ASP",
    "146": "C++",
    "147": "C#",
    "148": "Java",
    "149": "PHP",
    "150": "Python",
    "151": "VB",
    "152": "MSSQL",
    "153": "Oracle",
    "154": "Photoshop",
    "155": "Illustrator",
    "156": "AutoCAD",
    "157": "GIS",
    "158": "3D Design",
    "159": "Flash",
    "160": "Web Design",
    "161": "Linux",
    "162": "Macintosh",
    "163": "Solaris",
    "164": "Windows",
    "165": "MS Office",
    "166": "MySQL",
    # --- Special / Exams ---
    "167": "Integrated Programme",
    "168": "Adult Training",
    "169": "Group Tuition",
    "232": "SAT English",
    "233": "SAT Maths",
    # --- Sports ---
    "234": "Swimming",
    "235": "Tennis",
    "236": "Squash",
    "237": "Golf",
    "238": "Aerobics",
    "239": "Badminton",
    "240": "Table Tennis",
    "241": "Bowling",
    "242": "Yoga",
    "243": "Pilates",
    "244": "Ballet",
    "245": "Kickboxing",
    "246": "Dancing",
    "247": "Fencing",
    "248": "Karate",
    "249": "Taekwondo",
    "250": "Martial Arts",
    "251": "Taichi",
    "252": "Roller Blading",
}

TUTORCITY_LEVEL_ID_MAP: Dict[str, str] = {
    "1": "Pre-school",
    "2": "Primary",
    "3": "O Level",
    "4": "A Level",
    "5": "IB / IGCSE",
    "6": "Diploma / Degree",
    "7": "Music",
    "8": "Language",
    "9": "Computing",
    "10": "Special Skills",
    "11": "Sports",
}


def _first(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        for x in value:
            s = _first(x)
            if s:
                return s
        return None
    s = str(value).strip()
    return s or None


def _join_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        parts: List[str] = []
        for x in value:
            t = _join_text(x)
            if t:
                parts.append(t)
        seen = set()
        uniq: List[str] = []
        for p in parts:
            if p in seen:
                continue
            seen.add(p)
            uniq.append(p)
        return ", ".join(uniq)
    return str(value).strip()


def _parse_rate(rate: Optional[str]) -> Dict[str, Any]:
    # Keep the original string; best-effort min/max parsing for simple ranges like "50-80 p/h" or "$30/h".
    out: Dict[str, Any] = {"min": None, "max": None, "raw_text": rate}
    if not rate:
        return out
    cleaned = rate.replace("$", "").replace("/h", "").replace("p/h", "").replace("p.h", "").replace("per hour", "")
    cleaned = cleaned.replace("to", "-").replace("–", "-").replace("—", "-")
    parts = cleaned.split("-")
    nums: List[float] = []
    for p in parts:
        try:
            n = float(str(p).strip().split()[0])
            nums.append(n)
        except Exception:
            continue

    if len(nums) == 1:
        out["min"] = out["max"] = nums[0]
    elif len(nums) >= 2:
        out["min"] = float(min(nums))
        out["max"] = float(max(nums))
    return out


def _map_row(row: Dict[str, Any], source_label: str) -> Dict[str, Any]:
    assignment_code = _first(row.get("assignment_code"))
    subjects_raw = row.get("subjects") or []
    subject_ids = subjects_raw if isinstance(subjects_raw, list) else [subjects_raw] if subjects_raw else []
    subject_ids = [str(x).strip() for x in subject_ids if str(x).strip()]
    level_id = _first(row.get("level"))
    year = _first(row.get("year"))
    address = _first(row.get("address"))
    postal_code = _first(row.get("postal_code"))
    availability = _first(row.get("availability"))
    hourly_rate = row.get("hourly_rate")
    additional_remarks = _first(row.get("additional_remarks"))
    assignment_url = _first(row.get("assignment_url"))

    level_label = TUTORCITY_LEVEL_ID_MAP.get(str(level_id)) if level_id else None
    subject_labels: List[str] = []
    unmapped_subject_ids: List[str] = []
    for sid in subject_ids:
        label = TUTORCITY_SUBJECT_ID_MAP.get(str(sid))
        if label:
            subject_labels.append(label)
        else:
            unmapped_subject_ids.append(str(sid))

    # Build an academic display string (best-effort, API-provided fields only).
    subj_bits = [str(s).strip() for s in subject_labels if str(s).strip()]
    headline_parts = [str(x).strip() for x in (level_label, year) if str(x).strip()]
    headline = " ".join(headline_parts).strip()
    if subj_bits:
        headline = f"{headline} {' / '.join(subj_bits)}".strip()
    academic_display_text = headline or None

    # Deterministic time availability from the API availability string (if present).
    det_time = None
    if availability:
        try:
            det_time, _meta = extract_time_availability(raw_text=availability, normalized_text=normalize_text(availability))
        except Exception:
            det_time = None

    parsed: Dict[str, Any] = {
        "assignment_code": assignment_code,
        "academic_display_text": academic_display_text,
        "learning_mode": {"mode": None, "raw_text": None},
        "address": [address] if address else None,
        "postal_code": [postal_code] if postal_code else None,
        "nearest_mrt": None,
        "lesson_schedule": None,
        "start_date": None,
        "time_availability": det_time
        or {
            "explicit": {d: [] for d in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")},
            "estimated": {d: [] for d in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")},
            "note": availability or None,
        },
        "rate": _parse_rate(_first(hourly_rate)),
        "additional_remarks": additional_remarks,
    }

    signals, err = build_signals(parsed=parsed, raw_text="", normalized_text=academic_display_text)
    signals_meta = {"ok": False, "error": err} if err else {"ok": True, "signals": signals}

    source_raw = dict(row or {})
    source_mapped = {
        "mapping_version": TUTORCITY_MAPPING_VERSION,
        "assignment_code": assignment_code,
        "assignment_url": assignment_url,
        "level_id": level_id,
        "level": level_label,
        "year": year,
        "subject_ids": subject_ids,
        "subjects": subject_labels,
        "unmapped_subject_ids": unmapped_subject_ids,
    }

    payload: Dict[str, Any] = {
        "cid": f"tutorcity:{assignment_code or ''}",
        "channel_title": source_label,
        "channel_link": "https://tutorcity.sg",
        "channel_username": "tutorcity_sg",
        "message_id": assignment_code,
        "message_link": assignment_url,
        # TutorCity API does not provide a stable publish timestamp; treat first-seen as published.
        # `supabase_persist` will default published_at=now on insert and won't overwrite on updates.
        "parsed": parsed,
        "raw_text": _join_text([availability, additional_remarks]) or None,
        "meta": {"signals": signals_meta, "source_raw": source_raw, "source_mapped": source_mapped},
        "source_type": "tutorcity_api",
    }
    return payload


def fetch_api(url: str, limit: int, timeout_s: int, *, user_agent: str) -> List[Dict[str, Any]]:
    params = {"limit": limit}
    headers = {
        "accept": "application/json",
        "user-agent": user_agent or "TutorDexTutorCityFetcher/1.0",
    }
    resp = requests.get(url, params=params, headers=headers, timeout=timeout_s)
    if resp.status_code >= 400:
        raise RuntimeError(f"API error status={resp.status_code} body={resp.text[:300]}")
    data = resp.json()
    rows = data.get("all_assignments_data")
    if rows is None and isinstance(data.get("payload"), dict):
        rows = data["payload"].get("all_assignments_data")
    return rows if isinstance(rows, list) else []


def _row_score(row: Dict[str, Any]) -> tuple[int, int]:
    """
    Heuristic for picking the "best" row when TutorCity returns multiple entries
    with the same assignment_code (which represent updates).

    Returns (completeness_score, text_len_score).
    """
    def truthy(v: Any) -> bool:
        if v is None:
            return False
        if isinstance(v, (list, tuple, set, dict)):
            return len(v) > 0
        return bool(str(v).strip())

    score = 0
    for k in ("subjects", "level", "year", "address", "postal_code", "availability", "hourly_rate", "additional_remarks"):
        if truthy(row.get(k)):
            score += 1

    # Prefer richer text fields when scores tie.
    txt = ""
    for k in ("availability", "hourly_rate", "additional_remarks", "address"):
        v = row.get(k)
        if v is None:
            continue
        try:
            txt += " " + str(v)
        except Exception:
            continue
    txt_len = len(txt.strip())
    return int(score), int(txt_len)


def main() -> None:
    p = argparse.ArgumentParser(description="Fetch TutorCity API and persist/broadcast without LLM")
    p.add_argument("--limit", type=int, default=None, help="Number of rows to fetch (default from env or 50)")
    args = p.parse_args()

    cfg = load_aggregator_config()
    url = str(cfg.tutorcity_api_url or DEFAULT_URL).strip() or DEFAULT_URL
    limit = int(args.limit) if args.limit is not None else int(cfg.tutorcity_limit)
    timeout_s = int(cfg.tutorcity_timeout_seconds)
    user_agent = str(cfg.tutorcity_user_agent or "").strip() or "TutorDexTutorCityFetcher/1.0"
    source_label = "TutorCity"
    # Disable bumping for API rows: set bump_min_seconds extremely high.
    base_cfg = load_config_from_env()
    supa_cfg = SupabaseConfig(
        url=base_cfg.url,
        key=base_cfg.key,
        assignments_table=base_cfg.assignments_table,
        enabled=base_cfg.enabled,
        bump_min_seconds=10**9,
    )

    rows = fetch_api(url, limit, timeout_s, user_agent=user_agent)
    if not rows:
        print("No rows returned from API.")
        return

    # TutorCity can return multiple rows for the same assignment_code. Treat later/better rows as updates.
    best_by_code: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for row in rows:
        code = str((row or {}).get("assignment_code") or "").strip()
        if not code:
            continue
        if code not in best_by_code:
            best_by_code[code] = row
            order.append(code)
            continue
        prev = best_by_code.get(code) or {}
        if _row_score(row) >= _row_score(prev):
            best_by_code[code] = row

    for code in order:
        row = best_by_code.get(code)
        if not isinstance(row, dict):
            continue
        payload = _map_row(row, source_label)
        cid = payload.get("cid")
        with bind_log_context(cid=str(cid), channel=payload.get("channel_link"), message_id=payload.get("message_id"), step="tutorcity"):
            log_event(logger, logging.INFO, "tutorcity_row", assignment_code=payload["parsed"].get("assignment_code"), address=payload["parsed"].get("address"))
            res = persist_assignment_to_supabase(payload, cfg=supa_cfg)
            log_event(logger, logging.INFO, "tutorcity_persist_result", res=res)

            is_insert = bool(res.get("ok")) and str(res.get("action")).lower() == "inserted"
            if broadcast_assignments is not None and is_insert:
                try:
                    broadcast_assignments.send_broadcast(payload)
                except Exception:
                    logger.exception("tutorcity_broadcast_failed")
            if send_dms is not None and is_insert:
                try:
                    send_dms(payload)
                except Exception:
                    logger.exception("tutorcity_dm_failed")


if __name__ == "__main__":
    main()
