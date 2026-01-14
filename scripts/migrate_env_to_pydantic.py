#!/usr/bin/env python3
"""
Migrate legacy service .env files into the newer Pydantic templates.

Safety:
- Never prints secret values.
- Writes new .env files on disk.
- Creates timestamped backups of the legacy .env files.

What it does:
- Reads legacy env from:
  - TutorDexAggregator/.env
  - TutorDexBackend/.env
  - (optional) TutorDexWebsite/.env
- Renders from templates:
  - TutorDexAggregator/.env.example.pydantic
  - TutorDexBackend/.env.example.pydantic
  - TutorDexWebsite/.env.example.pydantic
- Fills values using explicit mapping + fallbacks.
- Appends any legacy keys not present in the template under a "LEGACY/EXTRA" section
  (so existing code keeps working during migration).
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Dict, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]


def _ts() -> str:
    # Use timezone-aware UTC timestamps (avoid deprecated utcnow()).
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d_%H%M%S")


def _parse_env(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    out: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("export "):
            s = s[len("export ") :].strip()
        if "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip()
        if not k:
            continue
        out[k] = v
    return out


def _backup(path: Path) -> Optional[Path]:
    if not path.exists():
        return None
    dest = path.with_suffix(path.suffix + f".legacy_{_ts()}")
    dest.write_text(path.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
    return dest


def _choose(d: Dict[str, str], keys: List[str]) -> Optional[str]:
    for k in keys:
        v = d.get(k)
        if v is None:
            continue
        # Keep exact value (may include quotes/comments); only treat empty/whitespace as missing.
        if str(v).strip() == "":
            continue
        return v
    return None


def _render_from_template(
    *,
    template_text: str,
    values: Dict[str, str],
    missing: List[str],
) -> str:
    """
    Replace lines that begin with KEY=... (ignoring leading whitespace).
    Keeps comments that trail the template line.
    """
    out_lines: List[str] = []
    for line in template_text.splitlines():
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            out_lines.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if not key or " " in key or "\t" in key:
            out_lines.append(line)
            continue

        if key in values and values[key] is not None:
            # Preserve any trailing comment on the template line.
            before, after = stripped.split("=", 1)
            comment = ""
            if "#" in after:
                _, tail = after.split("#", 1)
                comment = "#" + tail
            new_line = f"{before}={values[key]}{(' ' + comment) if comment else ''}".rstrip()
            out_lines.append(new_line)
        else:
            # Keep template default; record missing ONLY when explicitly marked REQUIRED.
            if stripped.startswith(f"{key}="):
                rhs = stripped.split("=", 1)[1]
                if "REQUIRED" in rhs:
                    missing.append(key)
            out_lines.append(line)
    return "\n".join(out_lines).rstrip() + "\n"


def _append_legacy_keys(*, rendered: str, legacy: Dict[str, str], template_keys: List[str]) -> str:
    extra_keys = sorted(set(legacy.keys()) - set(template_keys))
    if not extra_keys:
        return rendered

    lines = [rendered.rstrip(), "", "# =============================================================================", "# LEGACY/EXTRA (kept for compatibility during migration)", "# ============================================================================="]
    for k in extra_keys:
        lines.append(f"{k}={legacy[k]}")
    return "\n".join(lines).rstrip() + "\n"


def _template_keys(template_text: str) -> List[str]:
    keys: List[str] = []
    for line in template_text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k = s.split("=", 1)[0].strip()
        if k and " " not in k and "\t" not in k:
            keys.append(k)
    return keys


def migrate_service(
    *,
    name: str,
    env_path: Path,
    template_path: Path,
    out_path: Path,
    mappings: Dict[str, List[str]],
    default_fills: Dict[str, str],
) -> Tuple[List[str], Optional[Path]]:
    legacy = _parse_env(env_path)
    template = template_path.read_text(encoding="utf-8")
    template_keys = _template_keys(template)

    missing: List[str] = []
    values: Dict[str, str] = {}

    # Use explicit mappings first.
    for target_key, source_keys in mappings.items():
        chosen = _choose(legacy, source_keys)
        if chosen is not None:
            values[target_key] = chosen

    # Apply defaults for keys that are present in template but absent in legacy.
    for k, v in default_fills.items():
        if k not in values:
            values[k] = v

    rendered = _render_from_template(template_text=template, values=values, missing=missing)
    rendered = _append_legacy_keys(rendered=rendered, legacy=legacy, template_keys=template_keys)

    backup = _backup(env_path)
    out_path.write_text(rendered, encoding="utf-8")
    return (sorted(set(missing)), backup)


def main() -> None:
    missing_all: Dict[str, List[str]] = {}
    backups: Dict[str, str] = {}

    # Aggregator
    agg_env = REPO_ROOT / "TutorDexAggregator" / ".env"
    agg_tpl = REPO_ROOT / "TutorDexAggregator" / ".env.example.pydantic"
    # Load backend env first so we can carry shared values like SCHEMA_VERSION.
    backend_env_for_shared = _parse_env(REPO_ROOT / "TutorDexBackend" / ".env")
    schema_version_shared = _choose(backend_env_for_shared, ["SCHEMA_VERSION"]) or "2026-01-01"

    missing_agg, backup_agg = migrate_service(
        name="TutorDexAggregator",
        env_path=agg_env,
        template_path=agg_tpl,
        out_path=agg_env,
        mappings={
            "SUPABASE_URL": ["SUPABASE_URL_DOCKER", "SUPABASE_URL_HOST", "SUPABASE_URL"],
            "SUPABASE_KEY": ["SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_KEY"],
            "TELEGRAM_API_ID": ["TELEGRAM_API_ID", "TG_API_ID", "API_ID"],
            "TELEGRAM_API_HASH": ["TELEGRAM_API_HASH", "TG_API_HASH", "API_HASH"],
            # Prefer group bot token for channel posting; fall back to DM bot token.
            "TELEGRAM_BOT_TOKEN": ["GROUP_BOT_TOKEN", "DM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"],
            # Carry over LLM config.
            "LLM_API_URL": ["LLM_API_URL"],
            "LLM_MODEL_NAME": ["LLM_MODEL_NAME"],
            # Feature toggles.
            "OTEL_ENABLED": ["OTEL_ENABLED"],
            # Keep these consistent for future config adoption.
            "ENABLE_BROADCAST": ["EXTRACTION_WORKER_BROADCAST", "ENABLE_BROADCAST"],
            "ENABLE_DMS": ["EXTRACTION_WORKER_DMS", "ENABLE_DMS"],
        },
        default_fills={
            "SCHEMA_VERSION": schema_version_shared,
        },
    )
    if missing_agg:
        missing_all["TutorDexAggregator"] = missing_agg
    if backup_agg:
        backups["TutorDexAggregator"] = str(backup_agg)

    # Backend
    be_env = REPO_ROOT / "TutorDexBackend" / ".env"
    be_tpl = REPO_ROOT / "TutorDexBackend" / ".env.example.pydantic"
    missing_be, backup_be = migrate_service(
        name="TutorDexBackend",
        env_path=be_env,
        template_path=be_tpl,
        out_path=be_env,
        mappings={
            "SUPABASE_URL": ["SUPABASE_URL_DOCKER", "SUPABASE_URL_HOST", "SUPABASE_URL"],
            "SUPABASE_KEY": ["SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_KEY"],
            "APP_ENV": ["APP_ENV"],
            "AUTH_REQUIRED": ["AUTH_REQUIRED"],
            "FIREBASE_ADMIN_ENABLED": ["FIREBASE_ADMIN_ENABLED"],
            "FIREBASE_ADMIN_CREDENTIALS_PATH": ["FIREBASE_ADMIN_CREDENTIALS_PATH"],
            "ADMIN_API_KEY": ["ADMIN_API_KEY"],
            "REDIS_URL": ["REDIS_URL"],
            "REDIS_PREFIX": ["REDIS_PREFIX"],
            "CORS_ALLOW_ORIGINS": ["CORS_ALLOW_ORIGINS"],
            "OTEL_ENABLED": ["OTEL_ENABLED"],
            "SENTRY_DSN": ["SENTRY_DSN"],
            "SENTRY_ENVIRONMENT": ["SENTRY_ENVIRONMENT"],
        },
        default_fills={},
    )
    if missing_be:
        missing_all["TutorDexBackend"] = missing_be
    if backup_be:
        backups["TutorDexBackend"] = str(backup_be)

    # Website (optional; best-effort)
    web_env = REPO_ROOT / "TutorDexWebsite" / ".env"
    web_tpl = REPO_ROOT / "TutorDexWebsite" / ".env.example.pydantic"
    if web_tpl.exists():
        legacy_web = _parse_env(web_env)
        # Minimal: preserve any existing website env and fill backend URL from backend env if possible.
        backend_legacy = _parse_env(be_env)
        backend_public_url = _choose(backend_legacy, ["BACKEND_PUBLIC_URL"]) or None
        backend_local = "http://localhost:8000"
        web_values = dict(legacy_web)
        if backend_public_url:
            web_values.setdefault("VITE_BACKEND_API_URL", backend_public_url)
            web_values.setdefault("VITE_BACKEND_URL", backend_public_url)
        else:
            web_values.setdefault("VITE_BACKEND_API_URL", backend_local)
            web_values.setdefault("VITE_BACKEND_URL", backend_local)

        # Render by simple key=value output (template has many REQUIRED fields we can't infer safely).
        if not web_env.exists():
            web_env.write_text("", encoding="utf-8")
        backup_web = _backup(web_env)
        lines = [f"{k}={v}" for k, v in sorted(web_values.items())]
        web_env.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        if backup_web:
            backups["TutorDexWebsite"] = str(backup_web)

        # Record required website keys we cannot infer.
        required = [
            "VITE_FIREBASE_API_KEY",
            "VITE_FIREBASE_AUTH_DOMAIN",
            "VITE_FIREBASE_PROJECT_ID",
        ]
        missing_web = [k for k in required if (k not in web_values) or (str(web_values.get(k) or "").strip() == "")]
        if missing_web:
            missing_all["TutorDexWebsite"] = missing_web

    # Print summary WITHOUT secrets.
    print("env_migration_ok=1")
    for svc, b in backups.items():
        print(f"backup:{svc}={b}")
    for svc, keys in missing_all.items():
        print(f"missing:{svc}={','.join(keys)}")


if __name__ == "__main__":
    main()
