#!/usr/bin/env python3

import ast
import tokenize
from pathlib import Path


EXCLUDED_DIRS = {
    ".git",
    ".github",
    ".pytest_cache",
    ".ruff_cache",
    ".vscode",
    "__pycache__",
    ".import_linter_cache",
    "build",
    "dist",
    "env",
    "node_modules",
    "venv",
}


def iter_python_files(root: Path) -> list[Path]:
    python_files: list[Path] = []
    for path in root.rglob("*.py"):
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        python_files.append(path)
    return python_files


def read_source(path: Path) -> str:
    with tokenize.open(path) as fp:
        return fp.read()


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    violations: list[tuple[Path, int, str]] = []
    parse_errors: list[tuple[Path, str]] = []

    for path in iter_python_files(repo_root):
        try:
            source = read_source(path)
            tree = ast.parse(source, filename=str(path))
        except (OSError, UnicodeError) as exc:
            parse_errors.append((path, f"I/O error reading file: {exc}"))
            continue
        except SyntaxError as exc:
            parse_errors.append((path, f"SyntaxError: {exc.msg} (line {exc.lineno})"))
            continue

        lines = source.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                lineno = getattr(node, "lineno", 1)
                line = lines[lineno - 1].rstrip() if 1 <= lineno <= len(lines) else "except:"
                violations.append((path, lineno, line))

    if parse_errors:
        print("::error::Failed to scan Python files for bare except due to parse/read errors.")
        for path, message in parse_errors:
            rel = path.relative_to(repo_root)
            print(f"::error file={rel}::{message}")
        return 1

    if not violations:
        print("✓ No bare except found")
        return 0

    print("::error::Found bare except. Use swallow_exception() or specific exception types instead.")
    for path, lineno, line in violations:
        rel = path.relative_to(repo_root)
        print(
            f"::error file={rel},line={lineno}::"
            "Bare except detected. Use swallow_exception() or specific exception types."
        )
        print(f"{rel}:{lineno}: {line}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
