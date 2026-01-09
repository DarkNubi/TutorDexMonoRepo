"""Loader and normalizer for tutor-type taxonomy.

Provides utilities to map raw labels (and optional agency hints) to a
canonical tutor-type with a simple confidence score.
"""
from __future__ import annotations

import json
import os
import re
from difflib import get_close_matches
from typing import Dict, Optional, Tuple

_ROOT = os.path.join(os.path.dirname(__file__))
_TAXONOMY_FILE = os.path.join(_ROOT, "tutor_types.yaml")


def _load_yaml(path: str) -> Dict:
    try:
        import yaml
    except Exception:
        # lightweight fallback for environments without PyYAML.
        # the file is small and fairly stable; attempt a minimal parser by
        # converting YAML to JSON via a naive approach only for simple maps.
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        # This fallback is intentionally conservative.
        raise RuntimeError("PyYAML is required to load taxonomy YAML files: install pyyaml")

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


_TAXONOMY: Optional[Dict] = None
_ALIASES_FLAT: Optional[Dict[str, str]] = None


def _ensure_loaded() -> None:
    global _TAXONOMY, _ALIASES_FLAT
    if _TAXONOMY is not None:
        return
    _TAXONOMY = _load_yaml(_TAXONOMY_FILE)
    # build flat alias map -> canonical
    aliases = {}
    for canon, info in (_TAXONOMY.get("canonical") or {}).items():
        for a in info.get("aliases", []) or []:
            aliases[a.lower()] = canon
        # include display name
        display = info.get("display")
        if display:
            aliases[display.lower()] = canon
    # NOTE: we intentionally do NOT load per-agency alias files here. Maintain
    # a single shared alias list in `tutor_types.yaml` to keep mappings
    # consistent at scale.
    _ALIASES_FLAT = aliases


def normalize_label(label: str, agency: Optional[str] = None) -> Tuple[str, str, float]:
    """Normalize a raw label to (canonical, original, confidence).

    - Uses deterministic alias matches first.
    - Falls back to fuzzy matching via difflib.
    - Returns `unknown` canonical if no match.
    """
    if not label or not label.strip():
        return "unknown", "", 0.0
    _ensure_loaded()
    orig = label.strip()
    key = orig.lower()
    # quick exact alias match
    if key in _ALIASES_FLAT:
        return _ALIASES_FLAT[key], orig, 0.99

    # tokenized match: check each token and n-gram
    tokens = re.split(r"[^a-z0-9]+", key)
    tokens = [t for t in tokens if t]
    for t in tokens:
        if t in _ALIASES_FLAT:
            return _ALIASES_FLAT[t], orig, 0.9

    # fuzzy match against alias keys
    candidates = get_close_matches(key, list(_ALIASES_FLAT.keys()), n=3, cutoff=0.8)
    if candidates:
        return _ALIASES_FLAT[candidates[0]], orig, 0.75

    # try substring match against aliases
    for a, canon in _ALIASES_FLAT.items():
        if a in key or key in a:
            return canon, orig, 0.7

    return "unknown", orig, 0.0


if __name__ == "__main__":
    # simple manual test
    sample = ["PT", "full timer", "ex-moe", "fresh grad", "senior teacher", "unknown label"]
    for s in sample:
        print(s, "->", normalize_label(s))
