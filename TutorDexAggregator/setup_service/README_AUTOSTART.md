# TutorDex Auto-Start Setup Guide (Windows)

Container-first is recommended. Task Scheduler remains available if you want to run the Python apps directly on the host.

## Docker-first (recommended)
- From repo root: `docker compose up -d --build`
- Supabase: containers join `supabase_default`; set `SUPABASE_URL_DOCKER=http://supabase-kong:8000` in `TutorDexAggregator/.env`.
- LLM: keep `llama-server` on the Windows host; containers use `LLM_API_URL=http://host.docker.internal:1234`.

## Task Scheduler (non-docker)
This installs two tasks for the queue pipeline:
- `TutorDex-Collector` (runs `setup_service/start_collector_loop.bat`)
- `TutorDex-Worker` (runs `setup_service/start_extract_worker_loop.bat`)

Install (run PowerShell as Administrator):
```powershell
cd d:\TutorDex\TutorDexAggregator\setup_service
powershell -ExecutionPolicy Bypass -File install_task_scheduler.ps1
```

Start:
```powershell
Start-ScheduledTask -TaskName "TutorDex-Collector"
Start-ScheduledTask -TaskName "TutorDex-Worker"
```

Stop:
```powershell
Stop-ScheduledTask -TaskName "TutorDex-Collector"
Stop-ScheduledTask -TaskName "TutorDex-Worker"
```

Uninstall:
```powershell
cd d:\TutorDex\TutorDexAggregator\setup_service
powershell -ExecutionPolicy Bypass -File uninstall_task_scheduler.ps1
```

## Manual control (non-docker)
Run in two terminals:
```cmd
cd d:\TutorDex\TutorDexAggregator\setup_service
start_collector_loop.bat
```
```cmd
cd d:\TutorDex\TutorDexAggregator\setup_service
start_extract_worker_loop.bat
```

## Queue pipeline + llama-server helper
This starts llama-server (optional) + the collector + worker in separate consoles:
```cmd
cd d:\TutorDex\TutorDexAggregator\setup_service
start_queue_pipeline_llama.bat
```

## Troubleshooting
- Python not found: install Python 3 and ensure `python` (or `py -3`) is on PATH.
- Check if running:
  - `Get-Process python | Where-Object {$_.CommandLine -like "*collector.py*"}`
  - `Get-Process python | Where-Object {$_.CommandLine -like "*extract_worker.py*"}`
