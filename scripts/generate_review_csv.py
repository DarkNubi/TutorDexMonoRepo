"""Generate a human-review CSV from tutor_types JSONL output.

Reads JSONL lines produced by `scripts/backfill_tutor_types.py` (or similar) where
each line is a JSON object with `external_id`, `tutor_types`, `rate_breakdown`.

Writes a CSV with columns: external_id, original_label, canonical, confidence, unmapped, rate_min, rate_max, rate_text
Includes only entries with confidence below threshold or canonical == 'unknown'.
"""
import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def make_rows(obj: Dict[str, Any], thresh: float) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    ext = obj.get("external_id")
    tts = obj.get("tutor_types") or []
    rb = obj.get("rate_breakdown") or {}
    for t in tts:
        orig = t.get("original") or t.get("label") or ""
        canon = (t.get("canonical") or "unknown").lower()
        conf = t.get("confidence")
        try:
            conff = float(conf) if conf is not None else None
        except Exception:
            conff = None
        unmapped = 1 if canon == "unknown" else 0
        low = False
        if conff is None or conff < thresh:
            low = True
        if low or unmapped:
            rb_item = rb.get(canon) or {}
            out.append({
                "external_id": ext,
                "original_label": orig,
                "canonical": canon,
                "confidence": conff if conff is not None else "",
                "unmapped": unmapped,
                "rate_min": rb_item.get("min") or "",
                "rate_max": rb_item.get("max") or "",
                "rate_text": rb_item.get("original_text") or "",
            })
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="infile", required=True)
    p.add_argument("--out", dest="outfile", required=True)
    p.add_argument("--threshold", dest="threshold", type=float, default=0.6)
    args = p.parse_args()
    inp = Path(args.infile)
    outp = Path(args.outfile)
    rows_all: List[Dict[str, Any]] = []
    with inp.open("r", encoding="utf-8") as inf:
        for line in inf:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            rows = make_rows(obj, args.threshold)
            rows_all.extend(rows)

    if not rows_all:
        print("No low-confidence or unmapped items found.")
        return

    with outp.open("w", encoding="utf-8", newline="") as outf:
        writer = csv.DictWriter(outf, fieldnames=["external_id", "original_label", "canonical",
                                "confidence", "unmapped", "rate_min", "rate_max", "rate_text"])
        writer.writeheader()
        for r in rows_all:
            writer.writerow(r)
    print(f"Wrote {len(rows_all)} rows to {outp}")


if __name__ == "__main__":
    main()
