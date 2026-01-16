# Removed Files

This document tracks files/directories removed as part of legacy cleanup work (Phase C1).

## 2026-01-16

- `TutorDexAggregator/monitor_message_edits.py`
  - Legacy standalone script; not used by the current Docker Compose / queue worker pipeline.
- `TutorDexAggregator/setup_service/`
  - Legacy Windows task-scheduler scripts; superseded by Docker Compose workflows.
- `TutorDexAggregator/supabase_persist.py.backup`
  - Stale backup artifact; superseded by `TutorDexAggregator/supabase_persist_impl.py`.

