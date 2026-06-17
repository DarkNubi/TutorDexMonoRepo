#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

RULES = [
    (("TutorDexAggregator/",), ["docs/ARCHITECTURE.md", "docs/KNOWN_INVARIANTS.md", "docs/SYSTEM_INTERNAL.md", "docs/TESTING.md"]),
    (("TutorDexBackend/",), ["docs/ARCHITECTURE.md", "docs/SYSTEM_INTERNAL.md", "docs/TESTING.md"]),
    (("TutorDexWebsite/",), ["TutorDexWebsite/README.md", "docs/SYSTEM_INTERNAL.md", "docs/TESTING.md"]),
    (("shared/",), ["docs/KNOWN_INVARIANTS.md", "docs/SYSTEM_INTERNAL.md"]),
    (("scripts/ops/", "docker-compose.yml", ".github/workflows/"), ["docs/OPERATIONS.md", "docs/DEPLOYMENT_TOPOLOGY.md", "docs/TESTING.md", "docs/GENERATED_INVENTORY.md"]),
    (("observability/",), ["observability/README.md", "docs/OPERATIONS.md", "docs/DEPLOYMENT_TOPOLOGY.md"]),
    (("docs/", "AGENTS.md"), ["docs/DOCS_CATALOG.md", "scripts/docs_health.py"]),
]


def git_changed(base: str) -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--name-only", base, "--"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def docs_for(path: str) -> set[str]:
    out: set[str] = set()
    for prefixes, docs in RULES:
        if any(path == p or path.startswith(p) for p in prefixes):
            out.update(docs)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Advisory docs routing guard for TutorDex changes.")
    parser.add_argument("--base", default="HEAD")
    parser.add_argument("--changed-file", action="append", default=[])
    args = parser.parse_args()

    changed = list(args.changed_file) or git_changed(args.base)
    if not changed:
        print("TutorDex docs change guard: no changed files detected")
        return 0

    required: set[str] = set()
    for path in changed:
        required.update(docs_for(path))

    print("TutorDex docs change guard: advisory")
    print("Changed files:")
    for path in changed:
        print(f"- {path}")
    if required:
        print("Docs to inspect/update or explicitly skip in evidence:")
        for path in sorted(required):
            print(f"- {path}")
    else:
        print("No docs routing rule matched these paths.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

