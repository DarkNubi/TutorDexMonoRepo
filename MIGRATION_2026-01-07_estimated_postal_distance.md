# Migration Guide: Distance Calculation from Estimated Postal Codes

**Date**: 2026-01-07
**Feature**: Enhanced distance calculation to support estimated postal codes

## Overview

Previously, distance calculations only worked when an explicit postal code was available. This enhancement adds support for calculating distances from estimated postal codes as a fallback, and displays an "(estimated)" indicator in the UI when this occurs.

## Changes Required

### 1. Database Migration

Run the following SQL migrations in order:

```sql
-- 1. Add postal_coords_estimated column
-- File: TutorDexAggregator/supabase sqls/2026-01-07_postal_coords_estimated.sql
alter table public.assignments
  add column if not exists postal_coords_estimated boolean default false;

comment on column public.assignments.postal_coords_estimated is 
  'True when postal_lat/postal_lon were derived from postal_code_estimated rather than explicit postal_code';

-- 2. Update list_open_assignments_v2 function
-- File: TutorDexAggregator/supabase sqls/2026-01-07_update_list_open_assignments_v2.sql
-- (Run the complete function definition from the file)
```

### 2. Backend Changes

The backend has been updated to include the `postal_coords_estimated` field in the assignment response. No additional configuration is required.

### 3. Frontend Changes

The frontend automatically displays "(estimated)" next to distances calculated from estimated postal codes. No additional configuration is required.

## Behavior

### Coordinate Resolution Priority

1. **Explicit postal code**: If `postal_code` is available, geocode it first
2. **Estimated postal code**: If explicit geocoding fails or is unavailable, try the first `postal_code_estimated`
3. **No coordinates**: If both fail, no coordinates are set

### Distance Display

- **Explicit coordinates**: `~5.2 km` or `~12 km`
- **Estimated coordinates**: `~5.2 km (estimated)` or `~12 km (estimated)`

## Testing

Run the test suite to verify the changes:

```bash
# Unit tests for the new functionality
python -m unittest tests.test_postal_coords_estimated -v

# Existing tests to ensure no regression
python -m unittest tests.test_supabase_persist_signals_rollup -v

# Validate contracts
python shared/contracts/validate_contracts.py
```

## Rollback

If you need to rollback this change:

1. The `postal_coords_estimated` column can remain in the database (it will be ignored by older code)
2. Revert the `list_open_assignments_v2` function to the previous version
3. Revert backend and frontend code changes

## Notes

- The feature is backward compatible - older clients without the updated code will simply ignore the `postal_coords_estimated` field
- Distance calculation still requires Nominatim to be enabled (controlled by `DISABLE_NOMINATIM` environment variable)
- The fallback to estimated postal codes happens automatically during assignment persistence
