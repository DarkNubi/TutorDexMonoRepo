#!/usr/bin/env python3
"""
Flatten service .env files by removing migration-only markers and producing a single
continuous config file (no "LEGACY/EXTRA" section header), without printing secrets.

What it does (in-place):
- Removes any line containing "LEGACY/EXTRA".
- Removes the immediate blank line following that marker (if present).
- Normalizes line endings to "\n".

What it does NOT do:
- It does not change any KEY=VALUE pairs.
- It does not reorder keys.
- It does not print file contents.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse


@dataclass(frozen=True)
class Result:
    path: Path
    changed: bool
    removed_markers: int
    removed_blank_after: int


def flatten_env(path: Path) -> Result:
    original = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    out: list[str] = []
    removed_markers = 0
    removed_blank_after = 0
    skip_next_blank = False

    for line in original:
        if "LEGACY/EXTRA" in line:
            removed_markers += 1
            skip_next_blank = True
            continue

        if skip_next_blank:
            if line.strip() == "":
                removed_blank_after += 1
                skip_next_blank = False
                continue
            skip_next_blank = False

        out.append(line)

    new_text = "\n".join(out) + "\n"
    old_text = "\n".join(original) + "\n"
    changed = new_text != old_text
    if changed:
        path.write_text(new_text, encoding="utf-8")
    return Result(path=path, changed=changed, removed_markers=removed_markers, removed_blank_after=removed_blank_after)


def main() -> int:
    ap = argparse.ArgumentParser(description="Flatten .env files by removing LEGACY/EXTRA markers (no secrets printed).")
    ap.add_argument("paths", nargs="+", help="Env file paths to flatten")
    args = ap.parse_args()

    any_changed = False
    for p in args.paths:
        path = Path(p)
        if not path.exists():
            raise SystemExit(f"Missing file: {path}")
        res = flatten_env(path)
        any_changed = any_changed or res.changed
        # Only print filenames + counts, never contents.
        print(f"{res.path}: changed={res.changed} removed_markers={res.removed_markers} removed_blank_after={res.removed_blank_after}")

    return 0 if any_changed else 0


if __name__ == "__main__":
    raise SystemExit(main())

