# Metrics and log cardinality rules

Prometheus and Loki work best when labels stay **low-cardinality**.

## Allowed metric labels (typical)

- `component` (small fixed set)
- `pipeline_version`, `schema_version` (small set)
- `channel` (bounded set; keep to the configured channel list)
- `reason` (fixed enum; do not include raw error strings)
- `operation` (fixed enum)
- `stage` (fixed enum)
- `model` (bounded set)

## Never use as metric labels

- `assignment_id`, `raw_id`, `message_id`, `extraction_id`
- free-form exception text
- URLs

These must remain in logs only.

## Loki labels

Promtail labels are configured to keep high-cardinality identifiers as JSON fields (queryable),
but **not labels**. Use `compose_service`, `component`, `channel`, `pipeline_version`, `schema_version` for filtering.

