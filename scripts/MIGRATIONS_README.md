# Database Migration System

This directory contains database migration scripts for TutorDex.

## Overview

The migration system tracks which SQL files have been applied using the `public.schema_migrations` table. This ensures migrations are applied exactly once and in the correct order.

## Quick Start

### Prerequisites

```bash
pip install supabase
```

### Environment Setup

```bash
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="your-service-role-key"
```

### Apply Migrations

```bash
# Apply all pending migrations
python scripts/migrate.py

# Dry run (see what would be applied)
python scripts/migrate.py --dry-run

# Force re-apply a specific migration (use with caution)
python scripts/migrate.py --force-reapply 2025-12-22_add_postal_latlon
```

## How It Works

1. **Tracking Table**: The `00_migration_tracking.sql` file creates a `schema_migrations` table
2. **Migration Files**: SQL files in `TutorDexAggregator/supabase sqls/` are applied in alphabetical order
3. **Idempotency**: Each migration is recorded after successful execution
4. **Checksums**: Optional SHA256 checksums verify migration integrity

## Migration File Naming Convention

Format: `YYYY-MM-DD_description.sql`

Examples:
- `2025-12-22_add_postal_latlon.sql`
- `2026-01-03_subjects_taxonomy_v2.sql`

## Creating New Migrations

1. Create a new `.sql` file in `TutorDexAggregator/supabase sqls/`
2. Use the date-prefixed naming convention
3. Include `IF NOT EXISTS` or `IF EXISTS` clauses for idempotency
4. Test locally first with `--dry-run`

## Migration Best Practices

### ✅ DO:
- Use `CREATE TABLE IF NOT EXISTS`
- Use `CREATE INDEX IF NOT EXISTS`
- Add `IF EXISTS` to `DROP` statements
- Include descriptive comments
- Test migrations in development first
- Keep migrations small and focused

### ❌ DON'T:
- Delete or modify existing migration files (create new ones instead)
- Run migrations without backups in production
- Mix DDL and large data migrations in one file
- Use `DROP TABLE` without careful consideration

## Troubleshooting

### Migration Failed

If a migration fails:

1. Check the error message in the logs
2. Fix the SQL file
3. Manually remove the failed entry from `schema_migrations` if needed:
   ```sql
   DELETE FROM public.schema_migrations WHERE migration_name = 'failed-migration-name';
   ```
4. Re-run the migration script

### Checking Applied Migrations

```sql
SELECT migration_name, applied_at, execution_time_ms 
FROM public.schema_migrations 
ORDER BY applied_at DESC;
```

### Manual Migration Application

If the script doesn't work, you can apply migrations manually:

```sql
-- 1. Apply the SQL
\i TutorDexAggregator/supabase\ sqls/2025-12-22_add_postal_latlon.sql

-- 2. Record it
INSERT INTO public.schema_migrations (migration_name) 
VALUES ('2025-12-22_add_postal_latlon');
```

## CI/CD Integration

### GitHub Actions Example

```yaml
- name: Apply Database Migrations
  env:
    SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
    SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
  run: |
    pip install supabase
    python scripts/migrate.py
```

### Docker Deployment

Add to your deployment script:

```bash
docker exec tutordex-backend python scripts/migrate.py
```

## Limitations

⚠️ **Note**: The current implementation uses the Supabase REST API which has limitations for executing raw SQL. For production use, consider:

1. Using `psycopg2` for direct PostgreSQL connections
2. Using Supabase CLI (`supabase db diff` and `supabase db push`)
3. Manual application via Supabase dashboard SQL editor

## Future Enhancements

- [ ] Add rollback support (down migrations)
- [ ] Use `psycopg2` for direct SQL execution
- [ ] Add migration validation (syntax check before apply)
- [ ] Support for data migrations vs. schema migrations
- [ ] Migration dependencies and ordering constraints

## Related Files

- `TutorDexAggregator/supabase sqls/00_migration_tracking.sql` - Creates tracking table
- `scripts/migrate.py` - Migration application script
- `docs/CODEBASE_QUALITY_AUDIT_2026-01.md` - Priority 5 details
