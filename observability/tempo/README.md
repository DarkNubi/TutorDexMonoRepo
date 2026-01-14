# End-to-End Tracing with Tempo

TutorDex now has distributed tracing enabled by default using OpenTelemetry and Grafana Tempo.

## Architecture

```
┌──────────────┐     ┌──────────────────┐     ┌──────────┐     ┌─────────┐
│   Services   │────▶│ OTEL Collector   │────▶│  Tempo   │◀────│ Grafana │
│ (Backend,    │     │ (Port 4318/4317) │     │ (3200)   │     │ (3300)  │
│  Aggregator) │     └──────────────────┘     └──────────┘     └─────────┘
└──────────────┘
```

## Components

### 1. OpenTelemetry Instrumentation
All services automatically instrument HTTP requests, database calls, and custom spans using OTEL SDK.

### 2. OTEL Collector
Receives traces via OTLP protocol (HTTP: 4318, gRPC: 4317), processes them, and forwards to Tempo.

### 3. Tempo
Stores and queries traces. Provides trace IDs for correlation with logs and metrics.

### 4. Grafana
Visualizes traces, allows searching by service/span attributes, and correlates with logs (Loki) and metrics (Prometheus).

## Configuration

### Enable/Disable Tracing

Tracing is **enabled by default** in `docker-compose.yml`:

```yaml
environment:
  OTEL_ENABLED: "${OTEL_ENABLED:-1}"  # Default: 1 (enabled)
  OTEL_EXPORTER_OTLP_ENDPOINT: "http://otel-collector:4318"
  OTEL_SERVICE_NAME: "tutordex-backend"  # or tutordex-collector, etc.
```

To disable tracing temporarily:
```bash
export OTEL_ENABLED=0
docker compose up -d
```

### Service Names

Each service has a unique name for identification:
- `tutordex-backend` - API service
- `tutordex-collector` - Telegram collector
- `tutordex-aggregator-worker` - Extraction worker
- `tutordex-telegram-link-bot` - Telegram bot

## Usage

### Viewing Traces in Grafana

1. **Open Grafana**: http://localhost:3300
2. **Navigate**: Explore → Select "Tempo" datasource
3. **Search**:
   - By service name: `tutordex-backend`
   - By trace ID: `abc123...`
   - By span name: `telegram_message_seen`
   - By time range

### Trace a Request End-to-End

1. **Find a Telegram message** in collector logs:
   ```
   telegram_message_seen message_id=12345 channel=example trace_id=abc123...
   ```

2. **Copy trace ID** from logs

3. **Search in Grafana**: Paste trace ID into Tempo search

4. **View waterfall**: See the full journey:
   ```
   telegram_message_seen (collector)
     └─ enqueue_extraction
        └─ extraction_job (worker)
           └─ parse_assignment
              └─ persist_to_supabase
                 └─ broadcast_assignment
                    └─ send_dms
   ```

### Correlate with Logs

Tempo is configured to link to Loki logs (when Loki is enabled):

1. Click any span in a trace
2. Select "Logs for this span"
3. View structured logs for that specific operation

### Service Map

View service dependencies in Grafana:
1. Explore → Tempo
2. Click "Service Graph" tab
3. See call relationships between services

## Trace Context Propagation

### Automatic Propagation

OpenTelemetry automatically propagates trace context via HTTP headers (`traceparent`).

### Manual Propagation (for queue-based systems)

For asynchronous jobs (e.g., extraction queue), trace context is manually propagated:

```python
# In collector.py - starting a trace
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("telegram_message_seen") as span:
    span.set_attribute("channel", channel_link)
    span.set_attribute("message_id", message.id)
    
    # Get trace ID for propagation
    trace_id = format(span.get_span_context().trace_id, '032x')
    
    # Pass to extraction queue
    enqueue_extraction(raw_id, trace_id=trace_id)
```

```python
# In extract_worker.py - continuing the trace
from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, set_span_in_context

def process_extraction(job):
    if job.get("trace_id"):
        # Continue existing trace
        trace_id = int(job["trace_id"], 16)
        span_context = NonRecordingSpan(trace.SpanContext(
            trace_id=trace_id,
            span_id=0,
            is_remote=True,
            trace_flags=trace.TraceFlags(1)
        )).get_span_context()
        
        with tracer.start_as_current_span(
            "extraction_job",
            context=set_span_in_context(NonRecordingSpan(span_context))
        ):
            # Process job
            extract_and_persist(job)
```

## Custom Spans

Add custom spans to track specific operations:

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("custom_operation") as span:
    span.set_attribute("assignment_id", assignment_id)
    span.set_attribute("tutor_count", len(tutors))
    
    # Do work
    result = process_something()
    
    span.set_attribute("result_count", len(result))
```

## Troubleshooting

### No traces appearing

1. **Check OTEL is enabled**:
   ```bash
   docker compose exec backend env | grep OTEL
   # Should show: OTEL_ENABLED=1
   ```

2. **Check collector logs**:
   ```bash
   docker compose logs otel-collector
   # Look for "Traces received" messages
   ```

3. **Check Tempo logs**:
   ```bash
   docker compose logs tempo
   # Look for ingestion errors
   ```

### Traces not linking between services

1. **Verify trace context propagation**:
   - Check that HTTP clients pass `traceparent` header
   - For queues, verify trace_id is stored and retrieved

2. **Check service names**:
   - Ensure unique `OTEL_SERVICE_NAME` for each service
   - Names should match what you see in Grafana

### High cardinality warnings

If you see warnings about high cardinality attributes:

1. **Avoid high-cardinality attributes**:
   - ❌ Don't use: user IDs, timestamps, random UUIDs
   - ✅ Use: service names, operation types, status codes

2. **Use span events for high-cardinality data**:
   ```python
   span.add_event("assignment_matched", {
       "assignment_id": assignment_id  # OK as event attribute
   })
   ```

## Performance Impact

- **CPU**: <1% overhead for instrumentation
- **Memory**: ~10MB per service for OTEL SDK
- **Network**: ~1KB per trace sent to collector
- **Latency**: <1ms added to request processing

## Storage Retention

Traces are retained for **24 hours** (configurable in `tempo.yaml`).

For longer retention, update:
```yaml
# observability/tempo/tempo.yaml
compactor:
  compaction:
    block_retention: 168h  # 7 days
```

## Disabling Tracing in Development

To completely disable tracing (not recommended):

1. Set `OTEL_ENABLED=0` in `.env` files
2. Or remove tempo/otel-collector from docker-compose.yml

## References

- **OpenTelemetry Docs**: https://opentelemetry.io/docs/
- **Tempo Docs**: https://grafana.com/docs/tempo/latest/
- **OTEL Collector**: https://opentelemetry.io/docs/collector/
