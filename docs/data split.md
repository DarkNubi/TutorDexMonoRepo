Target state: Prod Supabase Postgres stays lean for live features; Analytics (warehouse/object store + OLAP engine) holds full history + backfill; a small metrics sync publishes only needed aggregates back into prod.

Step 1: Inventory & contracts

List current prod tables/columns used by the app (assignments, users, matches, freshness tiers, filters).
Identify query patterns and SLAs (API latency targets, max payload sizes, retention expectations).
Define “hot” retention window for prod (e.g., 30–90 days detailed rows; beyond that summarized or deleted).
Step 2: Define schemas

Prod: trim to operational needs (indexes for current filters, freshness tiers, matching); add compact summary tables if needed (e.g., weekly_counts_per_filter).
Analytics: design fact tables for assignments/messages and dimensions for tutor, agency, subject, channel; allow wide columns and history.
Backfill lands directly in analytics (not prod); agree on partitioning (by month) and clustering keys.
Step 3: Choose analytics stack & landing

Pick target: object store + DuckDB/Trino/BigQuery/Snowflake (whatever you can run—DuckDB+S3/minio is simplest self-host).
Define file format and partitioning (Parquet, partition by year/month).
Set up access credentials and network paths from the aggregator/backfill job.
Step 4: Data movement design

Real-time path: ingestion → prod (as today).
Change capture/export: periodic job (hourly/nightly) to dump new/changed prod rows to analytics (CSV/Parquet). If you need fresher, add CDC later.
Backfill path: historical fetch writes straight to analytics; optionally also a thin slice to prod if you need recent history for features.
Establish idempotency markers (ingestion_run_id, updated_at) to support replays.
Step 5: Metrics publishing (prod-facing stats)

Define the metrics needed in prod (e.g., past-7d assignments per filter, per subject, per channel; optional win_prob per tutor/filter).
Build an analytics job to compute these and push a compact table into prod (upsert by key, e.g., filter_id + bucket).
Schedule refresh cadence (hourly/daily) and size budgets (row counts, payload limits).
Step 6: Pipelines & ops

Implement/export scripts/jobs:
export_prod_to_analytics (nightly/hourly) writing Parquet to the warehouse.
backfill_to_analytics for historical pulls (runs once, chunked).
compute_and_publish_metrics that reads analytics and upserts into prod summary tables.
Add monitoring/alerts: job success/fail, row counts, freshness lag, size of prod tables.
Add retention/enforcement in prod (delete or archive beyond window).
Step 7: Migrations & rollout

Migrate prod schema to include summary tables/indexes; keep prod rows trimmed (apply retention).
Stand up analytics storage and test sample exports/queries.
Run a limited backfill to analytics and validate queries (trend, probability calc).
Enable metrics publishing into prod; wire the app to read the summary table instead of ad-hoc wide queries.
Document runbooks and env vars (paths, buckets, refresh intervals).
Step 8: Performance & cost tuning

Verify prod query plans with new indexes and smaller tables.
Size partitions and compression in analytics; consider clustering by subject/channel/date.
Cache frequently used aggregates in prod if needed.
Step 9: Testing & validation

Data quality checks on exports/backfills (row counts, hash totals, null audits).
Compare prod vs analytics row counts for overlapping windows.
Load/perf tests on prod APIs after retention is applied and summaries are in place.
Step 10: Decommission old paths

Remove any legacy “all-in-one” backfill into prod.
Update docs, diagrams, and ops scripts to reflect the split.