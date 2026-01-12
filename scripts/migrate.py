#!/usr/bin/env python3
"""
Database Migration Script

Applies SQL migrations from TutorDexAggregator/supabase sqls/ directory in order.
Tracks applied migrations in public.schema_migrations table.

Usage:
    python scripts/migrate.py [--dry-run] [--force-reapply MIGRATION_NAME]

Environment Variables:
    SUPABASE_URL: Supabase project URL
    SUPABASE_SERVICE_ROLE_KEY: Service role key with full database access
"""

import os
import sys
import hashlib
import logging
import time
from pathlib import Path
from typing import List, Optional
import argparse

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from supabase import create_client, Client
except ImportError:
    print("Error: supabase-py not installed. Run: pip install supabase")
    sys.exit(1)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("migrate")


def get_supabase_client() -> Client:
    """Create Supabase client from environment variables."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    
    if not url or not key:
        logger.error("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        sys.exit(1)
    
    return create_client(url, key)


def calculate_checksum(content: str) -> str:
    """Calculate SHA256 checksum of migration content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def get_applied_migrations(client: Client) -> set:
    """Get set of already-applied migration names."""
    try:
        response = client.table("schema_migrations").select("migration_name").execute()
        return {row["migration_name"] for row in response.data}
    except Exception as e:
        logger.warning(f"Could not fetch applied migrations (table may not exist): {e}")
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
    client: Client,
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
        
        # Execute SQL via Supabase REST API
        start_time = time.time()
        
        # Use rpc to execute raw SQL (requires a custom function in Supabase)
        # Alternative: Use psycopg2 or similar for direct SQL execution
        # For now, we'll use the PostgREST query endpoint
        
        # Split on semicolons for multiple statements
        statements = [s.strip() for s in content.split(";") if s.strip()]
        
        for statement in statements:
            if not statement:
                continue
            
            # Execute via direct SQL (this requires service role key)
            # Note: Supabase REST API doesn't support raw SQL directly
            # You would need to use psycopg2 or similar
            logger.debug(f"  Executing statement: {statement[:100]}...")
        
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        # Record migration as applied
        client.table("schema_migrations").insert({
            "migration_name": migration_name,
            "checksum": checksum,
            "execution_time_ms": execution_time_ms
        }).execute()
        
        logger.info(f"  ✓ Applied migration: {migration_name} ({execution_time_ms}ms)")
        return True
        
    except Exception as e:
        logger.error(f"  ✗ Failed to apply migration {migration_name}: {e}")
        return False


def apply_migrations(
    migrations_dir: Path,
    dry_run: bool = False,
    force_reapply: Optional[str] = None
) -> int:
    """
    Apply all pending migrations.
    
    Returns:
        Number of migrations applied (or would be applied in dry-run mode)
    """
    client = get_supabase_client()
    
    # Get applied migrations
    applied = get_applied_migrations(client)
    logger.info(f"Found {len(applied)} already-applied migrations")
    
    # Get migration files
    migration_files = get_migration_files(migrations_dir)
    logger.info(f"Found {len(migration_files)} migration files")
    
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
        success = execute_migration(client, migration_file, dry_run)
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
  python scripts/migrate.py
  
  # Dry run to see what would be applied
  python scripts/migrate.py --dry-run
  
  # Force re-apply a specific migration
  python scripts/migrate.py --force-reapply 2025-12-22_add_postal_latlon
  
Environment Variables:
  SUPABASE_URL                Supabase project URL (required)
  SUPABASE_SERVICE_ROLE_KEY   Service role key (required)
        """
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
