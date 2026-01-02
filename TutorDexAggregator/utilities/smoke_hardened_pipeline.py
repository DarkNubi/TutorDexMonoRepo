"""
Smoke test for the hardened extraction pipeline (no Supabase required).

This validates compatibility expectations for the rest of the project:
- deterministic time_availability (overwrites LLM output)
- deterministic academic signals (meta.signals) used to fill legacy `assignments` fields

Recommended run (no LLM required; uses a checked-in mock output):
  # from repo root
  LLM_MOCK_OUTPUT_FILE=TutorDexAggregator/utilities/mock_llm_outputs/v2_valid_sample.json \\
    python3 TutorDexAggregator/utilities/smoke_hardened_pipeline.py \\
      --file TutorDexAggregator/utilities/sample_assignment_post.sample.txt \\
      --chat t.me/TutorNowAssignments
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

AGG_DIR = Path(__file__).resolve().parents[1]
if str(AGG_DIR) not in sys.path:
    sys.path.insert(0, str(AGG_DIR))

from extract_key_info import extract_assignment_with_model, process_parsed_payload  # noqa: E402
from hard_validator import hard_validate  # noqa: E402
from normalize import normalize_text  # noqa: E402
from signals_builder import build_signals  # noqa: E402
from extractors.time_availability import extract_time_availability  # noqa: E402
from supabase_persist import _build_assignment_row  # noqa: E402


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _require(condition: bool, msg: str) -> None:
    if not condition:
        raise SystemExit(f"SMOKE_FAIL: {msg}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Smoke test hardened pipeline compatibility (no Supabase).")
    ap.add_argument("--file", "-f", required=True, help="Path to raw assignment post text file")
    ap.add_argument("--chat", default="t.me/sample", help="Chat ref (examples selection)")
    ap.add_argument("--print", dest="print_json", action="store_true", help="Print full debug JSON")
    args = ap.parse_args()

    raw_text = _read_text(Path(args.file)).strip()
    _require(bool(raw_text), "empty raw_text")

    normalized_text = normalize_text(raw_text)
    cid = f"smoke:{int(time.time())}"

    parsed = extract_assignment_with_model(raw_text, chat=str(args.chat), cid=cid) or {}
    payload: Dict[str, Any] = {
        "cid": cid,
        "channel_link": str(args.chat),
        "channel_title": "Smoke",
        "message_id": 1,
        "channel_id": -1,
        "message_link": "https://t.me/smoke/1",
        "raw_text": raw_text,
        "parsed": parsed,
    }

    # Enrich
    try:
        payload = process_parsed_payload(payload, False)
    except Exception:
        pass

    # Deterministic time overwrite
    det_ta, det_meta = extract_time_availability(raw_text=raw_text, normalized_text=normalized_text)
    if isinstance(payload.get("parsed"), dict):
        payload["parsed"]["time_availability"] = det_ta

    # Hard validate enforce
    cleaned, violations = hard_validate(payload.get("parsed") or {}, raw_text=raw_text, normalized_text=normalized_text)
    payload["parsed"] = cleaned

    # Signals
    signals, err = build_signals(parsed=payload.get("parsed") or {}, raw_text=raw_text, normalized_text=normalized_text)
    sig_meta: Optional[Dict[str, Any]] = None
    if err:
        sig_meta = {"ok": False, "error": err}
    else:
        sig_meta = {"ok": True, "signals": signals}

    payload["meta"] = {
        "normalization": {"chars": len(normalized_text)},
        "time_deterministic": {"ok": True, **(det_meta if isinstance(det_meta, dict) else {})},
        "hard_validation": {"mode": "enforce", "violations_count": len(violations)},
        "signals": sig_meta,
    }

    # Build legacy assignment row (what the website/backend read)
    os.environ["DISABLE_NOMINATIM"] = "1"
    row = _build_assignment_row(payload)

    # Basic assertions for compatibility
    ta = (payload.get("parsed") or {}).get("time_availability")
    _require(isinstance(ta, dict), "canonical_json.time_availability missing or not dict")
    for section in ("explicit", "estimated"):
        day_map = ta.get(section)
        _require(isinstance(day_map, dict), f"time_availability.{section} missing")
        _require(set(day_map.keys()) == {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}, f"time_availability.{section} day keys not complete")

    _require(isinstance(row.get("subjects"), list) and len(row.get("subjects")) > 0, "assignments.subjects not populated from meta.signals")
    _require(bool(str(row.get("level") or "").strip()), "assignments.level not populated from meta.signals")

    out = {"canonical_json": payload.get("parsed"), "meta": payload.get("meta"), "assignment_row": row}
    if args.print_json:
        print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("OK")
        print(json.dumps({"assignment_row.subjects": row.get("subjects"), "assignment_row.level": row.get("level")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

