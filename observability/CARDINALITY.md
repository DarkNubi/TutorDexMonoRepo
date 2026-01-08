# Metrics and log cardinality rules

Prometheus (and Loki, if used) work best when labels stay **low-cardinality**.

## Allowed metric labels (typical)


## Never use as metric labels


These must remain in logs only.

## Loki labels

Promtail labels are configured to keep high-cardinality identifiers as JSON fields (queryable),
but **not labels**. Use `compose_service`, `component`, `channel`, `pipeline_version`, `schema_version` for filtering.

