"""
Lightweight smoke test for extraction + enrichment + validation without broadcast or Supabase.

Usage:
  python utilities/smoke_extract.py --text "Some Telegram post text..."
  python utilities/smoke_extract.py --file sample.txt
"""

import argparse
import json
import sys
from pathlib import Path

from extract_key_info import extract_assignment_with_model, process_parsed_payload
from schema_validation import validate_parsed_assignment


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def main() -> None:
    p = argparse.ArgumentParser(description="Smoke test extraction + enrichment + validation")
    p.add_argument("--text", "-t", help="Raw Telegram message text")
    p.add_argument("--file", "-f", help="Path to file containing text")
    args = p.parse_args()

    raw_text = ""
    if args.text:
        raw_text = args.text
    elif args.file:
        fp = Path(args.file)
        if not fp.exists():
            print(f"File not found: {fp}")
            sys.exit(2)
        raw_text = _read_text(fp)
    else:
        print("Provide --text or --file")
        sys.exit(2)

    cid = f"smoke:{hash(raw_text) & 0xFFFFFFFF}"
    parsed = extract_assignment_with_model(raw_text, chat="", cid=cid) or {}
    payload = {
        "cid": cid,
        "raw_text": raw_text,
        "parsed": parsed,
    }
    enriched = process_parsed_payload(payload, False)
    ok, errs = validate_parsed_assignment(enriched.get("parsed") or {})

    print(json.dumps({"ok": ok, "errors": errs, "payload": enriched}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
