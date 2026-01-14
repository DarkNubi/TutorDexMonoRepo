"""
Supabase environment helpers (backend).

Supports a split configuration so the same repo can run:
- inside Docker (where `supabase-kong` is resolvable on the `supabase_default` network), and
- on the host (Windows/macOS/Linux) where Docker-only DNS names are not resolvable.

Env vars (recommended):
- SUPABASE_URL_DOCKER: e.g. http://supabase-kong:8000
- SUPABASE_URL_HOST:  e.g. http://127.0.0.1:54321 (or https://<project-ref>.supabase.co)

Fallback:
- SUPABASE_URL is still supported as a single value.
"""

def resolve_supabase_url() -> str:
    from shared.config import load_backend_config

    cfg = load_backend_config()
    return cfg.supabase_rest_url

