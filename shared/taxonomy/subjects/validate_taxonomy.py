from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

if __package__ in {None, ""}:
    # Allow running as a script: `python3 shared/taxonomy/subjects/validate_taxonomy.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from shared.taxonomy.subjects.canonicalizer import (  # noqa: E402
    DEFAULT_TAXONOMY_PATH,
    file_sha256,
    normalize_subject_label,
)


@dataclass(frozen=True)
class ValidationIssue:
    level: str  # error|warning
    message: str


def _load_json(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    if not isinstance(data, dict):
        raise ValueError("taxonomy must be a JSON object")
    return data


def _as_str_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        v = value.strip()
        return [v] if v else []
    if isinstance(value, list):
        out: List[str] = []
        for x in value:
            if isinstance(x, str) and x.strip():
                out.append(x.strip())
        return out
    return []


def validate_taxonomy(*, taxonomy_path: Path) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    data = _load_json(taxonomy_path)

    version = data.get("version")
    if not isinstance(version, int):
        issues.append(ValidationIssue("error", "taxonomy.version must be an int"))

    cats = data.get("general_categories")
    if not isinstance(cats, list) or not cats:
        issues.append(ValidationIssue("error", "taxonomy.general_categories must be a non-empty list"))
        cats = []

    cat_codes: Set[str] = set()
    for i, c in enumerate(cats):
        if not isinstance(c, dict):
            issues.append(ValidationIssue("error", f"general_categories[{i}] must be an object"))
            continue
        code = str(c.get("code") or "").strip()
        label = str(c.get("label") or "").strip()
        if not code or not label:
            issues.append(ValidationIssue("error", f"general_categories[{i}] missing code/label"))
            continue
        if code in cat_codes:
            issues.append(ValidationIssue("error", f"duplicate general category code: {code}"))
        cat_codes.add(code)

    subs = data.get("canonical_subjects")
    if not isinstance(subs, list) or not subs:
        issues.append(ValidationIssue("error", "taxonomy.canonical_subjects must be a non-empty list"))
        subs = []

    subject_codes: Set[str] = set()
    for i, s in enumerate(subs):
        if not isinstance(s, dict):
            issues.append(ValidationIssue("error", f"canonical_subjects[{i}] must be an object"))
            continue
        code = str(s.get("code") or "").strip()
        label = str(s.get("label") or "").strip()
        cat = str(s.get("general_category_code") or "").strip()
        if not code or not label or not cat:
            issues.append(ValidationIssue("error", f"canonical_subjects[{i}] missing code/label/general_category_code"))
            continue
        if code in subject_codes:
            issues.append(ValidationIssue("error", f"duplicate canonical subject code: {code}"))
        subject_codes.add(code)
        if cat not in cat_codes:
            issues.append(ValidationIssue("error", f"canonical_subjects[{i}] invalid general_category_code={cat} code={code}"))

    mappings = data.get("mappings") if isinstance(data.get("mappings"), dict) else {}
    by_level = mappings.get("by_level_subject_key") if isinstance(mappings.get("by_level_subject_key"), dict) else {}
    if not by_level:
        issues.append(ValidationIssue("error", "taxonomy.mappings.by_level_subject_key must be a non-empty object"))

    known_subject_keys: Set[str] = set()
    for lvl, m in by_level.items():
        if not isinstance(m, dict):
            issues.append(ValidationIssue("error", f"mappings.by_level_subject_key[{lvl}] must be an object"))
            continue
        for key, codes in m.items():
            k = str(key or "").strip()
            if not k:
                issues.append(ValidationIssue("error", f"empty subject_key under level={lvl}"))
                continue
            known_subject_keys.add(k)
            for code in _as_str_list(codes):
                if code not in subject_codes:
                    issues.append(ValidationIssue("error", f"mapping points to unknown code={code} (level={lvl}, key={k})"))

    raw_aliases = data.get("subject_aliases")
    if not isinstance(raw_aliases, dict) or not raw_aliases:
        issues.append(ValidationIssue("error", "taxonomy.subject_aliases must be a non-empty object"))
        raw_aliases = {}

    normalized_aliases: Dict[str, str] = {}
    for raw, key in raw_aliases.items():
        a = normalize_subject_label(str(raw))
        k = str(key or "").strip()
        if not a or not k:
            issues.append(ValidationIssue("error", f"invalid subject_alias: {raw!r} -> {key!r}"))
            continue
        if a in normalized_aliases and normalized_aliases[a] != k:
            issues.append(ValidationIssue("error", f"alias collision after normalization: {raw!r} and another alias both normalize to {a!r}"))
        normalized_aliases[a] = k
        if k not in known_subject_keys:
            issues.append(ValidationIssue("error", f"subject_alias target key has no mapping: alias={raw!r} key={k}"))

    levels = data.get("levels")
    if not isinstance(levels, list) or not levels:
        issues.append(ValidationIssue("error", "taxonomy.levels must be a non-empty list"))

    level_aliases = data.get("level_aliases")
    if not isinstance(level_aliases, dict) or not level_aliases:
        issues.append(ValidationIssue("error", "taxonomy.level_aliases must be a non-empty object"))
        level_aliases = {}

    level_set = {str(x) for x in (levels or []) if isinstance(x, str) and x.strip()}
    for raw, resolved in level_aliases.items():
        r = str(resolved or "").strip()
        if not r:
            issues.append(ValidationIssue("error", f"level_alias {raw!r} has empty target"))
            continue
        if level_set and r not in level_set:
            issues.append(ValidationIssue("error", f"level_alias {raw!r} targets unknown level: {r}"))

    return issues


def validate_sync(*, source: Path, copies: List[Path]) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    if not source.exists():
        return [ValidationIssue("error", f"missing source taxonomy: {source}")]
    src_hash = file_sha256(source)
    for p in copies:
        if not p.exists():
            issues.append(ValidationIssue("error", f"missing derived copy: {p}"))
            continue
        h = file_sha256(p)
        if h != src_hash:
            issues.append(ValidationIssue("error", f"derived copy drift: {p} (sha256 mismatch)"))
    return issues


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Validate TutorDex subjects taxonomy v2 and drift guards.")
    p.add_argument("--taxonomy", default=str(DEFAULT_TAXONOMY_PATH), help="Path to subjects_taxonomy_v2.json")
    p.add_argument("--check-sync", action="store_true", help="Fail if derived copies drift from source")
    args = p.parse_args(argv)

    taxonomy_path = Path(args.taxonomy).resolve()
    issues = validate_taxonomy(taxonomy_path=taxonomy_path)

    if args.check_sync:
        copies = [
            Path("TutorDexAggregator/taxonomy/subjects_taxonomy_v2.json").resolve(),
            Path("TutorDexWebsite/src/generated/subjects_taxonomy_v2.json").resolve(),
        ]
        issues.extend(validate_sync(source=taxonomy_path, copies=copies))

    errs = [i for i in issues if i.level == "error"]
    warns = [i for i in issues if i.level == "warning"]
    for i in errs + warns:
        print(f"{i.level.upper()}: {i.message}")
    if errs:
        print(f"FAILED: {len(errs)} errors, {len(warns)} warnings")
        return 1
    print(f"OK: {len(warns)} warnings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
