#!/usr/bin/env python3
"""
Refactor TutorDex service env files to match the migrated Pydantic config.

Goals
- Keep `.env` values exactly as-is (no secrets printed), but rewrite into a clean, grouped layout.
- Update `.env.example.pydantic` to match `shared/config.py` env var schema.
- Drop keys from `.env` only if they are NOT in schema and are NOT referenced anywhere in the repo.

Safety
- Never prints env values (only key names and counts).
- Never prints `.env` file contents.
"""

from __future__ import annotations

import argparse
import ast
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from shared.observability.exception_handler import swallow_exception


REPO_ROOT = Path(__file__).resolve().parents[1]


SERVICE_DIRS = {
    "aggregator": REPO_ROOT / "TutorDexAggregator",
    "backend": REPO_ROOT / "TutorDexBackend",
    "website": REPO_ROOT / "TutorDexWebsite",
}


CONFIG_PATH = REPO_ROOT / "shared" / "config.py"


def _safe_eval(node: ast.AST) -> Optional[Any]:
    # Evaluate simple literal defaults without importing user code.
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        v = _safe_eval(node.operand)
        if isinstance(v, (int, float)):
            return v if isinstance(node.op, ast.UAdd) else -v
        return None
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv)):
        a = _safe_eval(node.left)
        b = _safe_eval(node.right)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            try:
                if isinstance(node.op, ast.Add):
                    return a + b
                if isinstance(node.op, ast.Sub):
                    return a - b
                if isinstance(node.op, ast.Mult):
                    return a * b
                if isinstance(node.op, ast.Div):
                    return a / b
                if isinstance(node.op, ast.FloorDiv):
                    return a // b
            except Exception:
                return None
    return None


@dataclass(frozen=True)
class EnvField:
    env_name: str
    default: Optional[Any]


def _extract_aliaschoices_envs(node: ast.AST) -> list[str]:
    # validation_alias=AliasChoices("A", "B", ...)
    if not isinstance(node, ast.Call):
        return []
    # Allow either AliasChoices(...) or pydantic.AliasChoices(...)
    fn = node.func
    fn_name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else "")
    if fn_name != "AliasChoices":
        return []
    out: list[str] = []
    for a in node.args:
        if isinstance(a, ast.Constant) and isinstance(a.value, str):
            out.append(a.value)
    return out


def _field_default_from_field_call(call: ast.Call) -> Optional[Any]:
    # Field(default=..., validation_alias=...)
    for kw in call.keywords or []:
        if kw.arg == "default":
            return _safe_eval(kw.value)
    return None


def extract_config_env_fields(config_path: Path, class_name: str, *, env_prefix: str = "") -> list[EnvField]:
    tree = ast.parse(config_path.read_text(encoding="utf-8", errors="ignore"))
    fields: list[EnvField] = []

    class_node = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            class_node = node
            break
    if class_node is None:
        raise SystemExit(f"Could not find class {class_name} in {config_path}")

    for stmt in class_node.body:
        if not isinstance(stmt, ast.AnnAssign):
            continue
        if not isinstance(stmt.target, ast.Name):
            continue
        # Only consider Field(...) assignments (skip properties/validators etc.)
        if not isinstance(stmt.value, ast.Call):
            continue
        fn = stmt.value.func
        fn_name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else "")
        if fn_name != "Field":
            continue

        default = _field_default_from_field_call(stmt.value)

        alias_envs: list[str] = []
        for kw in stmt.value.keywords or []:
            if kw.arg == "validation_alias":
                alias_envs = _extract_aliaschoices_envs(kw.value)
                break
        if not alias_envs:
            # If no validation_alias, fall back to field_name uppercased (rare here).
            alias_envs = [stmt.target.id.upper()]

        # Use the first alias as the canonical env var name for templates.
        env_name = env_prefix + alias_envs[0]
        fields.append(EnvField(env_name=env_name, default=default))

    return fields


def _format_default(v: Optional[Any]) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        return v
    return ""


def _section_for_key(key: str) -> str:
    k = key.upper()
    if k.startswith("VITE_"):
        if "FIREBASE" in k:
            return "FIREBASE"
        if "SENTRY" in k:
            return "SENTRY"
        if "BACKEND" in k:
            return "BACKEND"
        return "VITE"
    if k.startswith("SUPABASE_"):
        return "SUPABASE"
    if k.startswith("REDIS_"):
        return "REDIS"
    if k.startswith("LLM_"):
        return "LLM"
    if k.startswith("EXTRACTION_") or k in {"SCHEMA_VERSION"}:
        return "PIPELINE"
    if k.startswith("TELEGRAM_") or k.startswith("TG_") or k in {"SESSION_STRING", "SESSION"}:
        return "TELEGRAM"
    if k.endswith("_BOT_TOKEN") or "BOT_TOKEN" in k:
        return "TELEGRAM"
    if k.startswith("BROADCAST_") or k in {"ENABLE_BROADCAST", "ENABLE_BROADCAST_TRACKING"}:
        return "BROADCAST"
    if k.startswith("DM_") or k in {"ENABLE_DMS"}:
        return "DMS"
    if k.startswith("OTEL_"):
        return "OTEL"
    if k.startswith("SENTRY_"):
        return "SENTRY"
    if k.startswith("LOG_") or k == "LOG_LEVEL":
        return "LOGGING"
    if k.startswith("RECOVERY_"):
        return "RECOVERY"
    if k.startswith("NOMINATIM_") or k == "DISABLE_NOMINATIM":
        return "GEOCODING"
    if k.startswith("SUBJECT_TAXONOMY_") or k.endswith("_TAXONOMY_PATH") or k.endswith("_GEOJSON_PATH") or k.endswith("_DATA_JSON_PATH"):
        return "ASSETS"
    if k.startswith("AB_"):
        return "TOOLS"
    if k.startswith("EDIT_MONITOR_"):
        return "TOOLS"
    if k.startswith("TUTORCITY_"):
        return "TUTORCITY"
    return "MISC"


def generate_example_pydantic(*, service: str, fields: list[EnvField]) -> str:
    header = [
        "# =============================================================================",
        f"# {service} Environment Configuration (Pydantic-Settings)",
        "# =============================================================================",
        "# Generated from `shared/config.py` (authoritative).",
        "# Copy to `.env` and fill in values as needed. Do not commit real `.env` files.",
        "# =============================================================================",
        "",
    ]

    sections_order = [
        "PIPELINE",
        "SUPABASE",
        "REDIS",
        "TELEGRAM",
        "LLM",
        "BROADCAST",
        "DMS",
        "LOGGING",
        "OTEL",
        "SENTRY",
        "RECOVERY",
        "GEOCODING",
        "ASSETS",
        "TUTORCITY",
        "TOOLS",
        "BACKEND",
        "FIREBASE",
        "VITE",
        "MISC",
    ]

    by_section: dict[str, list[EnvField]] = {}
    for f in fields:
        by_section.setdefault(_section_for_key(f.env_name), []).append(f)

    out: list[str] = list(header)
    for sec in sections_order:
        items = by_section.get(sec) or []
        if not items:
            continue
        out.append("# ----------------------------------------------------------------------------")
        out.append(f"# {sec}")
        out.append("# ----------------------------------------------------------------------------")
        for f in items:
            default_str = _format_default(f.default)
            out.append(f"{f.env_name}={default_str}")
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def parse_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        if not k:
            continue
        # Preserve the raw value portion as-is (including any quotes/spaces).
        data[k] = v.rstrip("\n")
    return data


def _rg_has_key_usage(key: str) -> bool:
    # Search for exact occurrences outside env files and docs.
    # We treat any code/compose usage as "referenced".
    cmd = [
        "rg",
        "-F",
        key,
        str(REPO_ROOT),
        "--glob",
        "!**/.git/**",
        "--glob",
        "!**/node_modules/**",
        "--glob",
        "!**/docs/**",
        "--glob",
        "!**/*.env*",
        "--glob",
        "!**/logs/**",
        "--glob",
        "!**/__pycache__/**",
    ]
    try:
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return r.returncode == 0
    except Exception:
        return False


@dataclass(frozen=True)
class RewriteResult:
    path: Path
    kept: int
    dropped: list[str]
    wrote_placeholders: int


def rewrite_env_from_fields(env_path: Path, fields: list[EnvField], *, allow_extra: bool = False) -> RewriteResult:
    existing = parse_env_file(env_path)
    allowed = {f.env_name for f in fields}

    dropped: list[str] = []
    extras: dict[str, str] = {}
    for k, v in existing.items():
        if k in allowed:
            continue
        # Keep only if referenced anywhere (non-doc, non-env).
        if _rg_has_key_usage(k):
            extras[k] = v
        else:
            dropped.append(k)

    # Build output with grouped layout; write real values for known keys, comment placeholders for missing.
    lines: list[str] = []
    lines.append("# =============================================================================")
    lines.append(f"# {env_path.parent.name} Runtime Environment (.env)")
    lines.append("# =============================================================================")
    lines.append("# Refactored to match `shared/config.py` (Pydantic config).")
    lines.append("# Values preserved; missing keys are left as commented placeholders.")
    lines.append("# =============================================================================")
    lines.append("")

    sections_order = [
        "PIPELINE",
        "SUPABASE",
        "REDIS",
        "TELEGRAM",
        "LLM",
        "BROADCAST",
        "DMS",
        "LOGGING",
        "OTEL",
        "SENTRY",
        "RECOVERY",
        "GEOCODING",
        "ASSETS",
        "TUTORCITY",
        "TOOLS",
        "BACKEND",
        "FIREBASE",
        "VITE",
        "MISC",
    ]
    by_section: dict[str, list[EnvField]] = {}
    for f in fields:
        by_section.setdefault(_section_for_key(f.env_name), []).append(f)

    wrote_placeholders = 0
    for sec in sections_order:
        items = by_section.get(sec) or []
        if not items:
            continue
        lines.append("# ----------------------------------------------------------------------------")
        lines.append(f"# {sec}")
        lines.append("# ----------------------------------------------------------------------------")
        for f in items:
            if f.env_name in existing:
                lines.append(f"{f.env_name}={existing[f.env_name]}")
            else:
                lines.append(f"# {f.env_name}={_format_default(f.default)}")
                wrote_placeholders += 1
        lines.append("")

    if extras and allow_extra:
        lines.append("# ----------------------------------------------------------------------------")
        lines.append("# EXTRA (referenced, not in shared/config.py)")
        lines.append("# ----------------------------------------------------------------------------")
        for k in sorted(extras.keys()):
            lines.append(f"{k}={extras[k]}")
        lines.append("")

    env_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    kept = len([k for k in existing.keys() if k in allowed]) + (len(extras) if allow_extra else 0)
    return RewriteResult(path=env_path, kept=kept, dropped=sorted(dropped), wrote_placeholders=wrote_placeholders)


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Refactor .env files + regenerate .env.example.pydantic from shared/config.py (no secrets printed).")
    ap.add_argument("--allow-extra", action="store_true", help="Keep referenced keys not present in shared/config.py (in an EXTRA section).")
    args = ap.parse_args()

    agg_fields = extract_config_env_fields(CONFIG_PATH, "AggregatorConfig")
    be_fields = extract_config_env_fields(CONFIG_PATH, "BackendConfig")
    web_fields = extract_config_env_fields(CONFIG_PATH, "WebsiteConfig", env_prefix="")  # WebsiteConfig already uses VITE_* aliases

    # Regenerate example templates (safe, no secrets).
    write_text(SERVICE_DIRS["aggregator"] / ".env.example.pydantic", generate_example_pydantic(service="TutorDexAggregator", fields=agg_fields))
    write_text(SERVICE_DIRS["backend"] / ".env.example.pydantic", generate_example_pydantic(service="TutorDexBackend", fields=be_fields))
    write_text(SERVICE_DIRS["website"] / ".env.example.pydantic", generate_example_pydantic(service="TutorDexWebsite", fields=web_fields))

    # Rewrite runtime env files (preserving values).
    res_agg = rewrite_env_from_fields(SERVICE_DIRS["aggregator"] / ".env", agg_fields, allow_extra=bool(args.allow_extra))
    res_be = rewrite_env_from_fields(SERVICE_DIRS["backend"] / ".env", be_fields, allow_extra=bool(args.allow_extra))
    res_web = rewrite_env_from_fields(SERVICE_DIRS["website"] / ".env", web_fields, allow_extra=bool(args.allow_extra))

    # Clean website legacy backups (safe to remove).
    for legacy in SERVICE_DIRS["website"].glob(".env.legacy_*"):
        try:
            legacy.unlink()
        except Exception as e:
            swallow_exception(e, context="legacy_env_cleanup", extra={"module": __name__})

    # Report only key names and counts.
    for r in (res_agg, res_be, res_web):
        print(f"{r.path}: kept={r.kept} dropped={len(r.dropped)} placeholders={r.wrote_placeholders}")
        if r.dropped:
            print(f"  dropped_keys: {', '.join(r.dropped)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

