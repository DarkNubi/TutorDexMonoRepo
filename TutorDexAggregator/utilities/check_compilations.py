"""
Quick harness for compilation detection.

Reads lines (one message per line) from a file and reports whether
`compilation_detection.is_compilation(...)` flags them.

Usage:
  python utilities/check_compilations.py --file compilations_sample.txt

If no file is provided, defaults to `TutorDexAggregator/compilations.jsonl`
and treats each line as JSON with a `raw_text` or `text` field.
"""

import argparse
import json
from pathlib import Path
from typing import Iterable, Tuple

from compilation_detection import is_compilation


def _load_plain_lines(path: Path) -> Iterable[str]:
    for ln in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = ln.strip()
        if s:
            yield s


def _load_jsonl_texts(path: Path) -> Iterable[str]:
    for ln in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = ln.strip()
        if not s:
            continue
        try:
            j = json.loads(s)
            if isinstance(j, dict):
                txt = j.get("raw_text") or j.get("text") or j.get("body")
                if txt:
                    yield str(txt)
        except Exception:
            continue


def _iter_messages(path: Path) -> Iterable[Tuple[int, str]]:
    if path.suffix.lower() == ".jsonl":
        loader = _load_jsonl_texts
    else:
        loader = _load_plain_lines
    for idx, msg in enumerate(loader(path), start=1):
        yield idx, msg


def main() -> None:
    p = argparse.ArgumentParser(description="Test compilation detection on sample messages")
    p.add_argument("--file", "-f", type=str, help="Path to text/jsonl file (one message per line)")
    args = p.parse_args()

    default = Path(__file__).resolve().parent.parent / "compilations.jsonl"
    path = Path(args.file) if args.file else default
    if not path.exists():
        print(f"File not found: {path}")
        return

    total = 0
    flagged = 0
    for idx, msg in _iter_messages(path):
        total += 1
        is_comp, detail = is_compilation(msg)
        if is_comp:
            flagged += 1
            print(f"[{idx}] COMPILATION: {detail} :: {msg[:200]}")

    print(f"\nChecked {total} messages. Flagged {flagged} as compilations.")


if __name__ == "__main__":
    main()
