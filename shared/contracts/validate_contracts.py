import argparse
from pathlib import Path


HERE = Path(__file__).resolve().parent
DEFAULT_SCHEMA_PATH = HERE / "assignment_row.schema.json"


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _check_equal(src: Path, dst: Path) -> tuple[bool, str]:
    if not dst.exists():
        return False, f"missing: {dst}"
    a = _read_bytes(src)
    b = _read_bytes(dst)
    if a != b:
        return False, f"mismatch: {dst} (run: python3 shared/contracts/sync_contract_artifacts.py)"
    return True, f"ok: {dst}"


def main() -> int:
    p = argparse.ArgumentParser(description="Validate shared contracts and drift guards.")
    p.add_argument("--schema", default=str(DEFAULT_SCHEMA_PATH), help="Path to assignment_row.schema.json")
    p.add_argument("--check-sync", action="store_true", help="Check derived copies match exactly")
    args = p.parse_args()

    src = Path(args.schema).resolve()
    if not src.exists():
        print(f"FAIL: missing schema: {src}")
        return 2

    if not args.check_sync:
        print("OK")
        return 0

    derived = [
        Path("TutorDexBackend/contracts/assignment_row.schema.json").resolve(),
        Path("TutorDexWebsite/src/generated/assignment_row.schema.json").resolve(),
    ]

    ok = True
    for dst in derived:
        same, msg = _check_equal(src, dst)
        print(("OK: " if same else "FAIL: ") + msg)
        ok = ok and same
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

