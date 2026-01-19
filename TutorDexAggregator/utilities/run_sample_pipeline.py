"""
Run a single sample post through the local extraction pipeline (NO Supabase).

This script is meant for fast iteration/debugging:
- normalize (always; raw text remains the source of truth)
- LLM extract (or mock via `LLM_MOCK_OUTPUT_FILE`)
- hard validate (off|report|enforce)
- deterministic signals (meta only)

Recommended (uses checked-in sample file and prints the full result JSON):
  python3 utilities/run_sample_pipeline.py --file utilities/sample_assignment_post.sample.txt --print-json

VS Code "Run" workflow:
- Edit the `sample = \"\"\"...\"\"\"` and `chat = \"t.me/...\"` inside the `if __name__ == \"__main__\":` block.
- Then hit Run; the script will use that sample by default when no CLI args are provided.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from shared.config import load_aggregator_config

AGG_DIR = Path(__file__).resolve().parents[1]
if str(AGG_DIR) not in sys.path:
    sys.path.insert(0, str(AGG_DIR))

from extract_key_info import extract_assignment_with_model, get_examples_meta, get_system_prompt_meta  # noqa: E402
from hard_validator import hard_validate  # noqa: E402
from normalize import normalize_text  # noqa: E402
from signals_builder import build_signals  # noqa: E402
from extractors.time_availability import extract_time_availability  # noqa: E402


def _truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _hard_mode(value: str) -> str:
    v = str(value or "").strip().lower()
    return v if v in {"off", "report", "enforce"} else "report"


def _safe_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _extract_sg_postal_codes(text: str) -> Optional[list[str]]:
    import re

    try:
        codes = re.findall(r"\b(\d{6})\b", str(text or ""))
    except Exception:
        codes = []
    seen = set()
    out: list[str] = []
    for c in codes:
        if c in seen:
            continue
        seen.add(c)
        out.append(c)
    return out or None


def _coerce_list_str(value: Any) -> Optional[list[str]]:
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        return [s] if s else None
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for x in value:
            out.extend(_coerce_list_str(x) or [])
        seen = set()
        uniq: list[str] = []
        for s in out:
            ss = str(s).strip()
            if not ss or ss in seen:
                continue
            seen.add(ss)
            uniq.append(ss)
        return uniq or None
    s2 = str(value).strip()
    return [s2] if s2 else None


def _fill_postal_code(parsed: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
    if not isinstance(parsed, dict):
        return {}
    existing = _coerce_list_str(parsed.get("postal_code"))
    if existing:
        parsed["postal_code"] = existing
        return parsed
    codes = _extract_sg_postal_codes(raw_text)
    parsed["postal_code"] = codes
    return parsed


def run_once(
    *,
    raw_text: str,
    chat: str,
    use_normalized_text_for_llm: bool,
    use_deterministic_time: bool,
    hard_validate_mode: str,
    enable_signals: bool,
    print_full_json: bool,
) -> int:
    raw_text = str(raw_text or "").strip()
    if not raw_text:
        raise SystemExit("Empty input text")

    normalized_text = normalize_text(raw_text)
    llm_input = normalized_text if bool(use_normalized_text_for_llm) else raw_text

    cid = f"sample:{int(time.time())}"

    print("\n" + "=" * 60)
    print("PROMPT CONTEXT")
    print("=" * 60)
    try:
        prompt_meta = get_system_prompt_meta()
        print(f"Prompt: sha256={prompt_meta.get('sha256')} source={prompt_meta.get('source')} chars={prompt_meta.get('chars')}")
    except Exception as e:
        print(f"Prompt: failed to resolve ({e})")
    try:
        ex_meta = get_examples_meta(chat)
        if ex_meta.get("enabled"):
            print(f"Examples: enabled=True file={ex_meta.get('file')} agency_key={ex_meta.get('agency_key')} variant={ex_meta.get('variant')}")
        else:
            print("Examples: enabled=False (set `LLM_INCLUDE_EXAMPLES=1` to enable few-shot)")
    except Exception as e:
        print(f"Examples: failed to resolve ({e})")
    print("=" * 60)

    parsed = extract_assignment_with_model(llm_input, chat=str(chat), cid=cid) or {}
    payload: Dict[str, Any] = {"cid": cid, "raw_text": raw_text, "parsed": parsed}

    # Deterministic postal-code fill (strict: only explicit 6-digit tokens in the post).
    try:
        if isinstance(payload.get("parsed"), dict):
            payload["parsed"] = _fill_postal_code(payload["parsed"], raw_text)
    except Exception:
        pass

    time_meta: Optional[Dict[str, Any]] = None
    if bool(use_deterministic_time):
        try:
            det_ta, det_meta = extract_time_availability(raw_text=raw_text, normalized_text=normalized_text)
            if isinstance(payload.get("parsed"), dict):
                payload["parsed"]["time_availability"] = det_ta
            time_meta = {"ok": True}
            if isinstance(det_meta, dict):
                time_meta.update(det_meta)
        except Exception as e:
            time_meta = {"ok": False, "error": str(e)}

    mode = _hard_mode(hard_validate_mode)
    hard_meta: Optional[Dict[str, Any]] = None
    if mode != "off":
        try:
            cleaned, violations = hard_validate(payload.get("parsed") or {}, raw_text=raw_text, normalized_text=normalized_text)
            hard_meta = {
                "mode": mode,
                "violations_count": int(len(violations)),
                "violations": violations[:50],
            }
            if mode == "enforce":
                payload["parsed"] = cleaned
        except Exception as e:
            hard_meta = {"mode": mode, "error": str(e)}

    signals_meta: Optional[Dict[str, Any]] = None
    if bool(enable_signals):
        try:
            signals, err = build_signals(parsed=payload.get("parsed") or {}, raw_text=raw_text, normalized_text=normalized_text)
            if err:
                signals_meta = {"ok": False, "error": err}
            else:
                signals_meta = {"ok": True, "signals": signals}
        except Exception as e:
            signals_meta = {"ok": False, "error": str(e)}

    out = {
        "canonical_json": payload.get("parsed") if isinstance(payload.get("parsed"), dict) else {},
        "meta": {
            "normalization": {"chars": len(normalized_text), "preview": normalized_text[:200]},
            "llm_input": "normalized" if bool(use_normalized_text_for_llm) else "raw",
            "time_deterministic": time_meta,
            "hard_validation": hard_meta,
            "signals": signals_meta,
            "mock_llm_output_file": _safe_str(load_aggregator_config().llm_mock_output_file),
        },
    }

    if print_full_json:
        print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    print("canonical_json:")
    print(json.dumps(out["canonical_json"], ensure_ascii=False, indent=2, sort_keys=True))
    print("\nmeta.signals:")
    print(json.dumps(((out.get("meta") or {}).get("signals")), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    # No-args VS Code "Run": use embedded sample/chat so examples selection works.
    if len(sys.argv) == 1:
        sample = """
SEC 3 COMBINED LITERATURE SS + Lit (Lord of the flies by William Golding) & SOCIAL STUDIES - Yew Mei Green Choa Chu Kang North 6 689575 (EX OR CURRENT TEACHER)

Frequency: 1 Lesson(s) Per Week, 1.5 Hours / Lesson

Timing: THURSDAY AT 6PM / SUNDAY AT 9AM

Budget Per Hour: S$70

Tutor Gender:  Female Tutor OR Male Tutor

Additional Requirement:EX OR CURRENT MOE TEACHER - Need to provide Teaching Materials instead of using assessment books. Female student from CHU. SS + Lit (Lord of the flies by William Golding)
If you’re interested, you can apply Here:  https://www.tutornow.sg/tuition-assignments
        """
        chat = "t.me/TutorNowAssignments"
        raise SystemExit(
            run_once(
                raw_text=sample,
                chat=chat,
                use_normalized_text_for_llm=False,
                use_deterministic_time=True,
                hard_validate_mode="enforce",
                enable_signals=True,
                print_full_json=True,
            )
        )

    parser = argparse.ArgumentParser(description="Run a sample post through the local pipeline (no Supabase).")
    parser.add_argument("--text", "-t", help="Raw post text")
    parser.add_argument("--file", "-f", help="Path to file containing raw post text")
    parser.add_argument("--chat", default="t.me/sample", help="Chat/channel ref used for examples selection (default: t.me/sample)")
    parser.add_argument("--print-json", action="store_true", help="Print full output JSON (canonical_json + meta)")
    parser.add_argument("--use-normalized-text-for-llm", action="store_true", help="Pass normalized_text to the LLM (default: false)")
    parser.add_argument("--use-deterministic-time", default="1", choices=["0", "1"],
                        help="Overwrite LLM time_availability with deterministic parser (default: 1)")
    parser.add_argument("--hard-validate-mode", default="enforce", choices=["off", "report", "enforce"])
    parser.add_argument("--enable-signals", default="1", choices=["0", "1"], help="Compute deterministic signals into meta (default: 1)")
    args = parser.parse_args()

    raw = ""
    if args.text:
        raw = args.text
    elif args.file:
        fp = Path(args.file)
        if not fp.exists():
            raise SystemExit(f"File not found: {fp}")
        raw = _read_text(fp)
    else:
        raise SystemExit("Provide --text or --file")

    raise SystemExit(
        run_once(
            raw_text=raw,
            chat=str(args.chat),
            use_normalized_text_for_llm=bool(args.use_normalized_text_for_llm),
            use_deterministic_time=str(args.use_deterministic_time).strip() == "1",
            hard_validate_mode=str(args.hard_validate_mode),
            enable_signals=str(args.enable_signals).strip() == "1",
            print_full_json=bool(args.print_json),
        )
    )
