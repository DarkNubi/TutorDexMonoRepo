"""Backfill/infer tutor types and per-type rates from a JSONL of historical messages.

Usage:
  python scripts/backfill_tutor_types.py --in data.jsonl --out out.jsonl

Input JSONL expects objects with at least `raw_text` and optionally `parsed` and `channel_title`.
Outputs JSONL lines with `external_id` (if present), `tutor_types`, and `rate_breakdown`.
"""
import argparse
import json
from pathlib import Path


def load_extractor():
    try:
        from TutorDexAggregator.extractors.tutor_types import extract_tutor_types
    except Exception:
        from extractors.tutor_types import extract_tutor_types
    return extract_tutor_types


def process(in_path: Path, out_path: Path):
    extract = load_extractor()
    with in_path.open("r", encoding="utf-8") as inf, out_path.open("w", encoding="utf-8") as outf:
        for line in inf:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            raw = obj.get("raw_text") or obj.get("text") or obj.get("message") or ""
            parsed = obj.get("parsed")
            agency = obj.get("channel_title") or obj.get("channel_link") or None
            try:
                res = extract(text=raw, parsed=parsed, agency=agency)
            except Exception as e:
                res = {"error": str(e)}
            out = {"external_id": obj.get("external_id"), "tutor_types": res.get("tutor_types"), "rate_breakdown": res.get("rate_breakdown")}
            outf.write(json.dumps(out, ensure_ascii=False) + "\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="infile", required=True)
    p.add_argument("--out", dest="outfile", required=True)
    args = p.parse_args()
    process(Path(args.infile), Path(args.outfile))


if __name__ == "__main__":
    main()
