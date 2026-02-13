#!/usr/bin/env python3
"""
Database Migration Script

Applies SQL migrations from TutorDexAggregator/supabase sqls/ directory in order.
Tracks applied migrations in public.schema_migrations table.

Usage:
    python scripts/migrate.py --db-container supabase-staging-db-1 [--dry-run]
    python scripts/migrate.py --db-container supabase-prod-db --apply-one 2026-02-11_ops_agent_gateway

Environment Variables:
    SUPABASE_DB_CONTAINER: Docker container name for the Supabase Postgres instance (recommended)
"""

import sys
import hashlib
import logging
import time
from pathlib import Path
from typing import List, Optional
import argparse
import subprocess
import os

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("migrate")


def _run_psql(*, container: str, sql: str, stdin_bytes: Optional[bytes] = None) -> str:
    cmd = [
        "docker",
        "exec",
        "-i",
        container,
        "psql",
        "-U",
        "postgres",
        "-d",
        "postgres",
        "-v",
        "ON_ERROR_STOP=1",
        "-t",
        "-A",
        "-c",
        sql,
    ]
    res = subprocess.run(cmd, input=stdin_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if res.returncode != 0:
        stderr = (res.stderr or b"").decode("utf-8", errors="ignore")[:800]
        raise RuntimeError(f"psql failed (code={res.returncode}): {stderr}")
    return (res.stdout or b"").decode("utf-8", errors="ignore")


def ensure_tracking_table(*, container: str) -> None:
    sql = """
    create table if not exists public.schema_migrations (
        id serial primary key,
        migration_name text unique not null,
        applied_at timestamptz default now() not null,
        checksum text,
        execution_time_ms integer
    );
    create index if not exists idx_schema_migrations_name on public.schema_migrations(migration_name);
    create index if not exists idx_schema_migrations_applied_at on public.schema_migrations(applied_at desc);
    """
    _run_psql(container=container, sql=sql)


def calculate_checksum(content: str) -> str:
    """Calculate SHA256 checksum of migration content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def get_applied_migrations(*, container: str) -> set:
    """Get set of already-applied migration names."""
    try:
        ensure_tracking_table(container=container)
        out = _run_psql(container=container, sql="select migration_name from public.schema_migrations;")
        rows = [ln.strip() for ln in out.splitlines() if ln.strip()]
        return set(rows)
    except Exception as e:
        logger.warning(f"Could not fetch applied migrations: {e}")
        return set()


def get_migration_files(migrations_dir: Path) -> List[Path]:
    """Get sorted list of SQL migration files."""
    # Get all .sql files except full schema dumps
    files = [
        f for f in migrations_dir.glob("*.sql")
        if not f.name.startswith("supabase_schema_full")
        and not f.name.startswith("supabase_rls_policies")
    ]
    return sorted(files)


def execute_migration(
    container: str,
    migration_file: Path,
    dry_run: bool = False
) -> bool:
    """Execute a single migration file."""
    migration_name = migration_file.stem
    logger.info(f"Processing migration: {migration_name}")

    try:
        content = migration_file.read_text(encoding="utf-8")
        checksum = calculate_checksum(content)

        if dry_run:
            logger.info(f"  [DRY RUN] Would apply migration: {migration_name}")
            logger.info(f"  [DRY RUN] Checksum: {checksum[:16]}...")
            logger.info(f"  [DRY RUN] Size: {len(content)} bytes")
            return True

        start_time = time.time()
        ensure_tracking_table(container=container)

        # Apply the whole file via stdin. Each migration file should be idempotent.
        cmd = [
            "docker",
            "exec",
            "-i",
            container,
            "psql",
            "-U",
            "postgres",
            "-d",
            "postgres",
            "-v",
            "ON_ERROR_STOP=1",
        ]
        res = subprocess.run(cmd, input=content.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if res.returncode != 0:
            stderr = (res.stderr or b"").decode("utf-8", errors="ignore")[:800]
            logger.error(f"  ✗ SQL apply failed for {migration_name}: {stderr}")
            return False

        execution_time_ms = int((time.time() - start_time) * 1000)

        # Record migration as applied (best-effort; idempotent).
        _run_psql(
            container=container,
            sql=(
                "insert into public.schema_migrations (migration_name, checksum, execution_time_ms) "
                f"values ('{migration_name}', '{checksum}', {execution_time_ms}) "
                "on conflict (migration_name) do nothing;"
            ),
        )

        logger.info(f"  ✓ Applied migration: {migration_name} ({execution_time_ms}ms)")
        return True

    except Exception as e:
        logger.error(f"  ✗ Failed to apply migration {migration_name}: {e}")
        return False


def apply_migrations(
    migrations_dir: Path,
    db_container: str,
    dry_run: bool = False,
    force_reapply: Optional[str] = None
) -> int:
    """
    Apply all pending migrations.

    Returns:
        Number of migrations applied (or would be applied in dry-run mode)
    """
    # Get applied migrations
    applied = get_applied_migrations(container=db_container)
    logger.info(f"Found {len(applied)} already-applied migrations")

    # Get migration files
    migration_files = get_migration_files(migrations_dir)
    logger.info(f"Found {len(migration_files)} migration files")

    # Safety: if tracking table is empty but DB has other tables, refuse bulk apply unless forced.
    if not dry_run and not force_reapply and len(applied) == 0:
        try:
            out = _run_psql(
                container=db_container,
                sql=(
                    "select count(*) from information_schema.tables "
                    "where table_schema='public' and table_name <> 'schema_migrations';"
                ),
            )
            existing_tables = int((out.strip() or "0").splitlines()[-1])
        except Exception:
            existing_tables = 0
        if existing_tables > 0 and len(migration_files) > 1:
            logger.error(
                "Refusing to apply multiple migrations because schema_migrations is empty but the DB is not empty. "
                "Use --apply-one to apply a single migration, or --force-reapply <name> for a specific file."
            )
            return 0

    # Filter pending migrations
    pending = []
    for f in migration_files:
        if force_reapply and f.stem == force_reapply:
            logger.warning(f"Force re-applying migration: {f.stem}")
            pending.append(f)
        elif f.stem not in applied:
            pending.append(f)

    if not pending:
        logger.info("✓ All migrations already applied. Nothing to do.")
        return 0

    logger.info(f"Found {len(pending)} pending migrations:")
    for f in pending:
        logger.info(f"  - {f.stem}")

    if dry_run:
        logger.info("\n[DRY RUN MODE] No changes will be made.\n")

    # Apply pending migrations
    applied_count = 0
    for migration_file in pending:
        success = execute_migration(db_container, migration_file, dry_run)
        if success:
            applied_count += 1
        else:
            logger.error(f"Migration failed: {migration_file.stem}")
            logger.error("Stopping migration process. Fix the error and re-run.")
            return applied_count

    logger.info(f"\n✓ Successfully applied {applied_count} migration(s)")
    return applied_count


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Apply database migrations to Supabase",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Apply all pending migrations
  python scripts/migrate.py --db-container supabase-prod-db

  # Dry run to see what would be applied
  python scripts/migrate.py --db-container supabase-prod-db --dry-run

  # Apply a single migration safely
  python scripts/migrate.py --db-container supabase-staging-db-1 --apply-one 2026-02-11_ops_agent_gateway

Environment Variables:
  SUPABASE_DB_CONTAINER       Docker container name for Supabase Postgres (optional if --db-container provided)
        """
    )

    parser.add_argument(
        "--db-container",
        default="",
        help="Docker container name for Supabase Postgres (e.g., supabase-prod-db or supabase-staging-db-1).",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be applied without making changes"
    )

    parser.add_argument(
        "--force-reapply",
        metavar="MIGRATION_NAME",
        help="Force re-apply a specific migration (use with caution)"
    )

    parser.add_argument(
        "--apply-one",
        metavar="MIGRATION_NAME",
        help="Apply exactly one migration by stem name (recommended for production).",
    )

    parser.add_argument(
        "--migrations-dir",
        type=Path,
        default=Path(__file__).parent.parent / "TutorDexAggregator" / "supabase sqls",
        help="Path to migrations directory"
    )

    args = parser.parse_args()

    # Validate migrations directory
    if not args.migrations_dir.exists():
        logger.error(f"Migrations directory not found: {args.migrations_dir}")
        sys.exit(1)

    db_container = str(args.db_container or "").strip() or str(os.environ.get("SUPABASE_DB_CONTAINER") or "").strip()
    if not db_container:
        logger.error("Missing --db-container (or SUPABASE_DB_CONTAINER).")
        sys.exit(1)

    if args.apply_one:
        args.force_reapply = str(args.apply_one).strip()

    apply_migrations(args.migrations_dir, db_container=db_container, dry_run=args.dry_run, force_reapply=args.force_reapply)

    # Apply migrations
    try:
        applied_count = apply_migrations(
            args.migrations_dir,
            dry_run=args.dry_run,
            force_reapply=args.force_reapply
        )
        sys.exit(0 if applied_count >= 0 else 1)
    except KeyboardInterrupt:
        logger.warning("\nMigration interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
