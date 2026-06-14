# Supabase Backup and Restore

TutorDex production currently uses a self-hosted Supabase Postgres container. Backups should be local artifacts outside git and must not expose env files, connection strings, passwords, service-role keys, or JWT secrets in logs.

## Current State

- No TutorDex/Supabase/Postgres backup timer was found in the visible systemd timers or user crontab during the 2026-06-14 recovery audit.
- No existing TutorDex/Supabase dump artifact was found in the shallow home-directory backup scan during that audit.
- The live production DB container was `supabase_db_supabase-prod`.
- The app can be repopulated from raw Telegram messages, but that is a recovery path, not a point-in-time database backup.

## Manual Backup

Create a custom-format dump:

```bash
TD_BACKUP_DIR=/home/insanepc/backups/tutordex/supabase \
  scripts/ops/supabase_backup.sh --env prod
```

If auto-detection fails, pass the container explicitly:

```bash
TD_BACKUP_DIR=/home/insanepc/backups/tutordex/supabase \
  scripts/ops/supabase_backup.sh --env prod --container supabase_db_supabase-prod
```

The script runs `pg_dump -Fc --no-owner --no-acl` inside the Supabase DB container, copies the dump to the backup directory, sets the artifact to mode `600`, and verifies the artifact with `pg_restore --list` before reporting success.

Use `--dry-run` to confirm the target container and output path without creating an artifact:

```bash
scripts/ops/supabase_backup.sh --env prod --dry-run
```

## Backup Verification

Safe, non-destructive checks:

```bash
ls -lh /home/insanepc/backups/tutordex/supabase/*.dump
pg_restore --list /home/insanepc/backups/tutordex/supabase/<artifact>.dump >/tmp/tutordex-restore-list.txt
```

If local `pg_restore` is unavailable, copy the dump into a staging or disposable Postgres container and run `pg_restore --list` there:

```bash
docker cp /home/insanepc/backups/tutordex/supabase/<artifact>.dump supabase_db_supabase-staging:/tmp/tutordex-verify.dump
docker exec supabase_db_supabase-staging pg_restore --list /tmp/tutordex-verify.dump >/tmp/tutordex-restore-list.txt
docker exec supabase_db_supabase-staging rm -f /tmp/tutordex-verify.dump
```

Do not inspect table data in group-visible output.

## Restore Path

Restores are destructive when run against an existing database. Prefer staging or a disposable Supabase stack first.

Staging/disposable rehearsal:

```bash
docker cp /home/insanepc/backups/tutordex/supabase/<artifact>.dump supabase_db_supabase-staging:/tmp/tutordex-restore.dump
docker exec supabase_db_supabase-staging \
  pg_restore --clean --if-exists --no-owner --no-acl -U postgres -d postgres /tmp/tutordex-restore.dump
docker exec supabase_db_supabase-staging rm -f /tmp/tutordex-restore.dump
```

Production restore shape, only after an explicit go/no-go and a fresh pre-restore backup:

```bash
scripts/ops/supabase_backup.sh --env prod --container supabase_db_supabase-prod
docker compose -f docker-compose.yml -p tutordex-prod --env-file .env.prod stop collector-tail aggregator-worker backend
docker cp /home/insanepc/backups/tutordex/supabase/<artifact>.dump supabase_db_supabase-prod:/tmp/tutordex-restore.dump
docker exec supabase_db_supabase-prod \
  pg_restore --clean --if-exists --no-owner --no-acl -U postgres -d postgres /tmp/tutordex-restore.dump
docker exec supabase_db_supabase-prod rm -f /tmp/tutordex-restore.dump
docker compose -f docker-compose.yml -p tutordex-prod --env-file .env.prod up -d backend collector-tail aggregator-worker
```

Post-restore checks:

```bash
curl -fsS http://127.0.0.1:8000/health/dependencies
scripts/ops/supabase_queue_health.sh --env prod
curl -fsS 'http://127.0.0.1:8000/assignments?limit=1'
```

## Limits

- `pg_restore --list` proves the dump is structurally readable; it does not prove application correctness.
- A staging restore proves PostgreSQL can replay the artifact; it does not prove public ingress, Firebase config, Telegram side effects, or the recovery queue are safe.
- Keep broadcast, DM, and freshness Telegram delete/edit side effects disabled until the restored state has been reviewed.
- Schedule automation should run the backup script, verify `pg_restore --list`, and alert if the latest successful artifact is too old. Do not store backup artifacts in git.
