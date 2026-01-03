from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from shared.taxonomy.subjects.canonicalizer import DEFAULT_TAXONOMY_PATH, file_sha256  # noqa: E402


def _copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())


def main() -> int:
    p = argparse.ArgumentParser(description="Sync subjects taxonomy v2 into app-local derived copies.")
    p.add_argument("--source", default=str(DEFAULT_TAXONOMY_PATH), help="Path to shared subjects_taxonomy_v2.json")
    args = p.parse_args()

    src = Path(args.source).resolve()
    if not src.exists():
        raise SystemExit(f"Missing source: {src}")

    targets = [
        Path("TutorDexAggregator/taxonomy/subjects_taxonomy_v2.json").resolve(),
        Path("TutorDexWebsite/src/generated/subjects_taxonomy_v2.json").resolve(),
    ]

    for dst in targets:
        _copy(src, dst)

    src_hash = file_sha256(src)
    for dst in targets:
        h = file_sha256(dst) if dst.exists() else "missing"
        if h != src_hash:
            raise SystemExit(f"Copy mismatch: {dst}")

    print("OK: synced subjects taxonomy v2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
