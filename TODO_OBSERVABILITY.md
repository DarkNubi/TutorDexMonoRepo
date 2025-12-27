# TutorDex Observability TODOs (Post-Beta)

Keep the current Telegram-based monitor for small scale. When usage grows, move toward standard observability tooling:

## Sentry (error tracking)
- Add Sentry SDK to `TutorDexBackend` (FastAPI) for exception + performance monitoring.
- Configure environments (`dev`/`staging`/`prod`) and release versioning.
- Add alert routing (email/Telegram/Slack) for high error rate / regressions.

## Prometheus + Grafana (metrics + dashboards)
- Expose metrics endpoints:
  - Backend: request count/latency/error rate, Redis ops latency/errors, Supabase ops latency/errors.
  - Aggregator: messages processed, skipped by reason, LLM latency, Supabase latency, Telegram send latency, DM send latency, rate-limit counts.
- Deploy Prometheus to scrape metrics and define alert rules.
- Deploy Grafana dashboards (SLO-style views + ops debugging).

## Loki (logs)
- Ship logs to Loki (Grafana Agent / Promtail).
- Add log panels and log-to-metrics correlations (e.g., `llm_extract_failed` spikes).

## Tracing (optional)
- Add OpenTelemetry tracing to correlate website/back-end requests and background jobs.

---

## Supabase product analytics (v3)

The infra observability above answers “is it up?”. This section answers “is the loop working?” using existing tables:
- `public.analytics_events` (event log: `event_type`, `event_time`, `meta`)
- `public.assignments` (supply + status)
- `public.telegram_messages_raw` / `public.telegram_extractions` / `public.ingestion_runs` (pipeline health)
- `public.assignment_clicks` / `public.broadcast_messages` (Telegram click-through proxy)

### Event taxonomy (`analytics_events.event_type`)

Use short, stable, snake_case event names. Keep `meta` small and consistent.

Tutor/account
- `auth_login` (`meta`: `surface=website`)
- `preferences_update` (`meta`: changed keys, e.g. `{"changed":["subjects","levels","postal_code"]}`)
- `telegram_link_success` (`meta`: `surface=website|bot`)
- `notifications_pause` / `notifications_resume` (`meta`: `reason`, `duration_hours` if applicable)

Assignment discovery (website)
- `assignment_list_view` (`meta`: `filters`, `sort`, `cursor`, `surface=website`)
- `assignment_view` (`meta`: `surface=website`, `list_position`, `filters_hash`)
- `assignment_save` / `assignment_unsave`
- `assignment_hide` (`meta`: `reason=too_far|rate_low|not_interested|duplicate|other`)

Application intent/outcomes (tutor-reported where needed)
- `assignment_apply_click` (`meta`: `surface=website|telegram`, `method=external|one_click`)
- `assignment_apply_submit` (`meta`: `method=one_click`, `answers_count`)
- `assignment_reply_received` (`meta`: `reply_time_minutes` if known)
- `assignment_no_reply` (`meta`: `days_waited`)
- `assignment_filled_report` (`meta`: `source=tutor|agency|inferred`)
- `assignment_scam_report` (`meta`: `category`, `notes` optional)

Delivery (server-side; emit only if you can map to `user_id`)
- `notify_sent` (`meta`: `surface=telegram_dm|email|web_push`, `batch_id`, `match_score`)
- `notify_click` (`meta`: `surface=telegram_dm|telegram_channel|website`, `link_type=assignment`)

Recommended shared `meta` keys
- `surface`: `website|telegram_dm|telegram_channel|backend`
- `client`: `web|backend|aggregator`
- `version`: app/build version
- `filters`: object (only for list events; avoid storing raw free-text)
- `list_position`: 0-based index for ranking evaluation
- `experiment`: optional `{name,variant}`

### KPI queries (Supabase Postgres)

Notes:
- Telegram has no “open”; use clicks as the proxy (via `assignment_clicks` or `notify_click`).
- Replace `:start`/`:end` with your dates, or drop them for “all time”.

**Event volume by day**
```sql
select
  date_trunc('day', event_time) as day,
  event_type,
  count(*) as events
from public.analytics_events
where event_time >= :start and event_time < :end
group by 1, 2
order by 1 desc, 3 desc;
```

**WAU (weekly active tutors)**
```sql
select
  date_trunc('week', event_time) as week,
  count(distinct user_id) as wau
from public.analytics_events
where user_id is not null
  and event_time >= :start and event_time < :end
  and event_type in (
    'assignment_list_view',
    'assignment_view',
    'assignment_apply_click',
    'preferences_update'
  )
group by 1
order by 1 desc;
```

**Preference tuning rate (weekly)**
```sql
with w as (
  select date_trunc('week', event_time) as week, user_id
  from public.analytics_events
  where event_type = 'preferences_update'
    and user_id is not null
    and event_time >= :start and event_time < :end
  group by 1, 2
),
active as (
  select date_trunc('week', event_time) as week, user_id
  from public.analytics_events
  where user_id is not null
    and event_time >= :start and event_time < :end
    and event_type in ('assignment_list_view','assignment_view','assignment_apply_click')
  group by 1, 2
)
select
  active.week,
  count(distinct w.user_id) as users_who_tuned,
  count(distinct active.user_id) as active_users,
  round(count(distinct w.user_id)::numeric / nullif(count(distinct active.user_id), 0), 4) as tune_rate
from active
left join w on w.week = active.week and w.user_id = active.user_id
group by 1
order by 1 desc;
```

**Apply rate (views → apply click)**
```sql
with base as (
  select
    date_trunc('week', event_time) as week,
    event_type,
    count(*) as c
  from public.analytics_events
  where event_time >= :start and event_time < :end
    and event_type in ('assignment_view','assignment_apply_click')
  group by 1, 2
)
select
  week,
  sum(c) filter (where event_type = 'assignment_view') as views,
  sum(c) filter (where event_type = 'assignment_apply_click') as apply_clicks,
  round(
    (sum(c) filter (where event_type = 'assignment_apply_click'))::numeric /
    nullif(sum(c) filter (where event_type = 'assignment_view'), 0),
    4
  ) as apply_rate
from base
group by 1
order by 1 desc;
```

**“Dead-end” rate (no reply / scam / filled complaints per apply)**
```sql
with w as (
  select date_trunc('week', event_time) as week, event_type, count(*) as c
  from public.analytics_events
  where event_time >= :start and event_time < :end
    and event_type in (
      'assignment_apply_click',
      'assignment_no_reply',
      'assignment_scam_report',
      'assignment_filled_report'
    )
  group by 1, 2
)
select
  week,
  sum(c) filter (where event_type = 'assignment_apply_click') as applies,
  sum(c) filter (where event_type = 'assignment_no_reply') as no_reply,
  sum(c) filter (where event_type = 'assignment_scam_report') as scams,
  sum(c) filter (where event_type = 'assignment_filled_report') as filled_reports,
  round(
    (sum(c) filter (where event_type in ('assignment_no_reply','assignment_scam_report','assignment_filled_report')))::numeric /
    nullif(sum(c) filter (where event_type = 'assignment_apply_click'), 0),
    4
  ) as dead_end_rate
from w
group by 1
order by 1 desc;
```

**Market supply: new assignments per day + open/filled mix**
```sql
select
  date_trunc('day', created_at) as day,
  count(*) as created,
  count(*) filter (where status = 'open') as open,
  count(*) filter (where status <> 'open') as not_open
from public.assignments
where created_at >= :start and created_at < :end
group by 1
order by 1 desc;
```

**Time-to-fill proxy (created → first filled report)**
```sql
select
  date_trunc('week', a.created_at) as week,
  percentile_cont(0.5) within group (order by extract(epoch from (e.event_time - a.created_at))/3600.0) as p50_hours_to_filled_report,
  percentile_cont(0.9) within group (order by extract(epoch from (e.event_time - a.created_at))/3600.0) as p90_hours_to_filled_report,
  count(*) as n
from public.analytics_events e
join public.assignments a on a.id = e.assignment_id
where e.event_type = 'assignment_filled_report'
  and e.assignment_id is not null
  and a.created_at >= :start and a.created_at < :end
group by 1
order by 1 desc;
```

**Pipeline health: extraction outcomes (daily)**
```sql
select
  date_trunc('day', created_at) as day,
  status,
  count(*) as n
from public.telegram_extractions
where created_at >= :start and created_at < :end
group by 1, 2
order by 1 desc, 3 desc;
```

**Pipeline health: ingestion run error rates**
```sql
select
  date_trunc('day', ir.started_at) as day,
  count(*) as runs,
  count(*) filter (where ir.status = 'ok') as ok_runs,
  count(*) filter (where ir.status <> 'ok') as bad_runs,
  sum(rp.error_count) as errors,
  sum(rp.scanned_count) as scanned,
  sum(rp.inserted_count) as inserted,
  sum(rp.updated_count) as updated
from public.ingestion_runs ir
left join public.ingestion_run_progress rp on rp.run_id = ir.id
where ir.started_at >= :start and ir.started_at < :end
group by 1
order by 1 desc;
```

**Telegram click-through proxy (channel broadcasts)**
```sql
select
  date_trunc('day', last_click_at) as day,
  count(*) as assignments_with_clicks,
  sum(clicks) as total_clicks
from public.assignment_clicks
where last_click_at >= :start and last_click_at < :end
group by 1
order by 1 desc;
```

### Minimal “v3 loop” implementation checklist
- Emit `assignment_list_view`, `assignment_view`, `assignment_apply_click` from the website via `POST /analytics/event`.
- Emit `preferences_update` whenever `/me/tutor` is saved (include `meta.changed` keys).
- Add tutor-side reporting UI that emits: `assignment_filled_report`, `assignment_no_reply`, `assignment_scam_report`.
- If/when you can map DM recipients to `user_id`, emit `notify_sent` and `notify_click` for true notification funnel metrics.
