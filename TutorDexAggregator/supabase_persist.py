"""
Thin entrypoint wrapper for Supabase persistence.

All implementation lives in `supabase_persist_impl.py` to keep this file small.
"""

from supabase_persist_impl import *  # noqa: F403


def _normalize_sg_postal_code(postal_code: str) -> str:
    """Compatibility shim for legacy callers/tests (patchable via this module)."""
    return str(normalize_sg_postal_code(postal_code) or "").strip()  # type: ignore[name-defined]  # noqa: F405


def _geocode_sg_postal(postal_code: str, *, timeout: int = 10):
    """Compatibility shim for legacy callers/tests (patchable via this module)."""
    return geocode_sg_postal(postal_code, timeout=timeout)  # type: ignore[name-defined]  # noqa: F405


def _build_assignment_row(payload):
    """Compatibility shim for legacy callers/tests (patchable via this module)."""
    return build_assignment_row(payload, geocode_func=_geocode_sg_postal)  # type: ignore[name-defined]  # noqa: F405


def _merge_patch_body(*, existing, incoming_row, force_upgrade: bool = False):
    """Compatibility shim for legacy callers/tests (patchable via this module)."""
    return merge_patch_body(existing=existing, incoming_row=incoming_row, force_upgrade=force_upgrade)  # type: ignore[name-defined]  # noqa: F405
