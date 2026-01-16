# ADR-0001: Consolidate Supabase Client Implementations

**Date**: 2026-01-16  
**Status**: Implemented

## Context

Multiple Supabase REST client wrappers existed across services, causing:
- duplicated maintenance effort (bug fixes + schema changes)
- inconsistent headers/timeouts/retry behavior
- divergent error handling (including RPC edge cases)

## Decision

Consolidate Supabase REST access behind a single implementation: `shared/supabase_client.py`.

The shared client provides:
- consistent auth header handling
- connection pooling via `requests.Session`
- retry logic for transient failures
- RPC HTTP `300` detection support (when using `SupabaseClient.rpc(...)`)

## Consequences

**Positive**
- single source of truth for Supabase HTTP behavior
- simpler future changes (timeouts, retries, auth, observability hooks)

**Negative**
- migration touches multiple call sites
- callers that previously accessed a pre-authenticated `session` directly must use client methods instead

## Implementation Notes

- Aggregator persistence and raw-ingest stores now construct clients via `shared/supabase_client.py`
- Backend store now uses `shared/supabase_client.py`
- Legacy duplicate client wrappers and backup files removed (see `docs/REMOVED_FILES.md`)

