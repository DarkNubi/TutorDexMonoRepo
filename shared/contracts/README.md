# Contracts (Shared API Schemas)

This directory contains shared, versioned API contracts that are consumed across:
- `TutorDexBackend/` (FastAPI)
- `TutorDexWebsite/` (static frontend)

## Assignment row contract

`assignment_row.schema.json` defines the JSON shape of each `items[]` element returned by:
- `GET /assignments` (backend)

This mirrors the output of the Supabase RPC `public.list_open_assignments_v2` (with `total_count` removed by the backend wrapper).

## Drift guard

Generated copies must match exactly:
- `TutorDexBackend/contracts/assignment_row.schema.json`
- `TutorDexWebsite/src/generated/assignment_row.schema.json`

Update workflow:
1. Edit `shared/contracts/assignment_row.schema.json`
2. Run `python3 shared/contracts/sync_contract_artifacts.py`
3. Verify with `python3 shared/contracts/validate_contracts.py --check-sync`

