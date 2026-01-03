import shutil
from pathlib import Path


HERE = Path(__file__).resolve().parent
DEFAULT_SCHEMA_PATH = HERE / "assignment_row.schema.json"


def main() -> int:
    src = DEFAULT_SCHEMA_PATH.resolve()
    if not src.exists():
        raise SystemExit(f"missing schema: {src}")

    targets = [
        (Path("TutorDexBackend/contracts/assignment_row.schema.json").resolve(), True),
        (Path("TutorDexWebsite/src/generated/assignment_row.schema.json").resolve(), True),
    ]

    for dst, make_parent in targets:
        if make_parent:
            dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)

    print("OK: synced contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

