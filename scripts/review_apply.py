"""Apply human-reviewed tutor-type corrections to the shared taxonomy YAML.

Expected input CSV columns:
  - original_label: raw label observed in message (required)
  - canonical: current canonical suggested by extractor (may be 'unknown')
  - correct_canonical: OPTIONAL corrected canonical value provided by reviewer

Behavior:
  - If `correct_canonical` is provided, use that as the target canonical name.
  - Otherwise use the `canonical` column. If neither present, skip row.
  - For each mapping, add `original_label` to the canonical entry's `aliases` if not already present.
  - If the canonical entry does not exist, create it with `display`: title-cased canonical and `aliases`: [original_label].
  - Creates a timestamped backup of the taxonomy before writing.

Usage:
  python scripts/review_apply.py --in review.csv --taxonomy shared/taxonomy/tutor_types.yaml --backup-dir backups --dry-run
"""
from __future__ import annotations

import argparse
import csv
import datetime
from pathlib import Path
from typing import Dict, List

try:
    import yaml
except Exception:
    raise RuntimeError("PyYAML is required: pip install PyYAML")


def load_taxonomy(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def write_taxonomy(path: Path, data: Dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def apply_corrections(rows: List[Dict[str, str]], taxonomy: Dict) -> Dict:
    # Ensure top-level structure exists
    if not isinstance(taxonomy, dict):
        taxonomy = {}
    canon_map = taxonomy.setdefault("canonical", {})

    for r in rows:
        orig = (r.get("original_label") or "").strip()
        if not orig:
            continue
        target = (r.get("correct_canonical") or r.get("canonical") or "").strip()
        if not target:
            continue
        # canonical keys are stored as-is; normalize to lower for matching existing keys
        # but keep the provided canonical key string as the canonical name.
        key = target
        entry = canon_map.get(key)
        if entry is None:
            # create new entry
            entry = {"display": key.title(), "aliases": [orig]}
            canon_map[key] = entry
            continue
        # ensure aliases list exists
        aliases = entry.get("aliases") or []
        # normalize comparison
        if not any(a.strip().lower() == orig.lower() for a in aliases):
            aliases.append(orig)
            entry["aliases"] = aliases

    taxonomy["canonical"] = canon_map
    return taxonomy


def read_csv(path: Path) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            out.append(row)
    return out


def backup_file(path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    target = backup_dir / f"tutor_types.yaml.bak.{ts}"
    with path.open("rb") as src, target.open("wb") as dst:
        dst.write(src.read())
    return target


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="infile", required=True)
    p.add_argument("--taxonomy", dest="taxonomy", default="shared/taxonomy/tutor_types.yaml")
    p.add_argument("--backup-dir", dest="backup_dir", default="backups")
    p.add_argument("--dry-run", dest="dry_run", action="store_true")
    args = p.parse_args()

    infile = Path(args.infile)
    tax_path = Path(args.taxonomy)
    backup_dir = Path(args.backup_dir)

    if not infile.exists():
        print(f"Input CSV not found: {infile}")
        return
    if not tax_path.exists():
        print(f"Taxonomy file not found: {tax_path}")
        return

    rows = read_csv(infile)
    if not rows:
        print("No rows in input CSV.")
        return

    taxonomy = load_taxonomy(tax_path)

    if args.dry_run:
        new_tax = apply_corrections(rows, taxonomy.copy())
        print("Dry run - preview of changes:\n")
        print(yaml.safe_dump(new_tax, sort_keys=False, allow_unicode=True))
        return

    # backup
    bak = backup_file(tax_path, backup_dir)
    print(f"Backed up {tax_path} -> {bak}")

    updated = apply_corrections(rows, taxonomy)
    write_taxonomy(tax_path, updated)
    print(f"Updated taxonomy written to {tax_path}")


if __name__ == "__main__":
    main()
