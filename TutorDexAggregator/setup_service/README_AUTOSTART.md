# TutorDex Auto-Start Setup Guide

This guide explains how to keep TutorDex running automatically on Windows. Container-first is recommended; Task Scheduler remains available if you want to run the Python app directly.

## Docker-first (recommended)
- From repo root: `docker compose up -d --build`
- Supabase: join the `supabase_default` network (the compose file already does this) and set `SUPABASE_URL_DOCKER=http://supabase-kong:8000`.
- Llama: keep `llama-server` on the Windows host; containers use `LLM_API_URL=http://host.docker.internal:1234`.
- Freshness tiers: enable the sidecar with `docker compose --profile tiers up -d freshness-tiers` (uses `.env` defaults or `FRESHNESS_TIERS_*` overrides).

## Quick Setup (Recommended)

### 1. Install as Windows Task Scheduler Job (non-docker)

**Run as Administrator:**

```powershell
cd d:\TutorDex\TutorDexAggregator\setup_service
powershell -ExecutionPolicy Bypass -File install_task_scheduler.ps1
```

This will:
- ✅ Auto-start when Windows boots
- ✅ Auto-restart if it crashes (up to 3 times)
- ✅ Keep running in a loop indefinitely
- ✅ Run with your user permissions

### 2. Start the Task

```powershell
Start-ScheduledTask -TaskName "TutorDex-Aggregator"
```

### 3. Check Status

```powershell
Get-ScheduledTask -TaskName "TutorDex-Aggregator" | Format-List
```

### 4. View Running Task

Open Task Manager → More details → Details tab → Look for `python.exe` or `cmd.exe` processes

---

## Manual Control

### Start Manually (One-time)
```cmd
cd d:\TutorDex\TutorDexAggregator\setup_service
start_tutordex.bat
```

### Start with Auto-Restart Loop (24/7)
```cmd
cd d:\TutorDex\TutorDexAggregator\setup_service
start_tutordex_loop.bat
```

### Start Monitor + Alerts Loop (24/7)
Run this in a separate scheduled task (recommended) so you still get alerts if the aggregator crashes:
```cmd
cd d:\TutorDex\TutorDexAggregator\setup_service
start_monitor_loop.bat
```

---

## Queue pipeline + llama-server (recommended for full-history backfill)

This mode runs the raw collector + extraction workers against your Supabase queue, using `llama-server` as the local OpenAI-compatible LLM endpoint.

1) Configure `llama-server` paths (edit):
- `TutorDexAggregator/setup_service/start_llama_server_loop.bat`
  - `LLAMA_SERVER_EXE=...`
  - `LLAMA_MODEL_PATH=...`

2) Ensure Supabase queue RPC is applied:
- `TutorDexAggregator/supabase sqls/2025-12-22_extraction_queue_rpc.sql`
- (Recommended) Simplify extractions table (single-stage):
  - `TutorDexAggregator/supabase sqls/2025-12-23_simplify_telegram_extractions.sql`

3) Start queue pipeline (one command, one console):
```cmd
cd d:\TutorDex\TutorDexAggregator
python runner.py queue --days 30 --workers 4 --start-llama
```

Notes:
- This does a one-shot backfill for the last `--days` and then starts `collector.py tail` + N extraction workers.
- Broadcast + DMs are disabled by default by the queue launcher; Nominatim stays enabled.

### Freshness tiers (use Docker sidecar)
- Apply DB migration: `TutorDexAggregator/migrations/2025-12-17_add_freshness_tier.sql`
- Enable in env: `FRESHNESS_TIER_ENABLED=true` (and optionally tune `FRESHNESS_TIERS_INTERVAL_SECONDS`, `FRESHNESS_TIERS_ARGS`)
- Start the sidecar: `docker compose --profile tiers up -d freshness-tiers`
- Legacy Task Scheduler scripts for freshness tiers were removed; if you installed an old `TutorDex-FreshnessTiers` task, remove it via Task Scheduler or `Unregister-ScheduledTask -TaskName "TutorDex-FreshnessTiers" -Confirm:$false`.

### Stop the Scheduled Task
```powershell
Stop-ScheduledTask -TaskName "TutorDex-Aggregator"
```

### Uninstall the Scheduled Task
```powershell
cd d:\TutorDex\TutorDexAggregator\setup_service
powershell -ExecutionPolicy Bypass -File uninstall_task_scheduler.ps1
```

---

## Alternative Methods

### Method 2: Windows Startup Folder (Simple but less reliable)

1. Press `Win + R`, type `shell:startup`, press Enter
2. Create a shortcut to `start_tutordex_loop.bat` in that folder
3. Restart your PC

**Limitations:**
- Only starts when you log in (not on boot)
- Won't run if you're logged out
- Less reliable than Task Scheduler

### Method 3: Install as Windows Service (Advanced)

Use NSSM (Non-Sucking Service Manager):

1. Download NSSM: https://nssm.cc/download
2. Extract and run as Administrator:
   ```cmd
   nssm install TutorDex
   ```
3. Configure:
   - Path: `C:\Path\To\Python\python.exe`
   - Startup directory: `d:\TutorDex\TutorDexAggregator`
   - Arguments: `runner.py start`
4. Set to start automatically

**Benefits:**
- Runs as a true Windows service
- Starts before login
- More robust restart handling

---

## Monitoring & Logs

### View Logs
Logs are printed to stdout/stderr by default. To save logs:

```cmd
python runner.py start >> logs\tutordex_%date:~-4,4%%date:~-7,2%%date:~-10,2%.log 2>&1
```

Or modify `start_tutordex_loop.bat` to add logging:
```batch
python runner.py start >> logs\tutordex.log 2>&1
```

### Check if Running
```powershell
Get-Process python | Where-Object {$_.CommandLine -like "*runner.py*"}
```

### Task Scheduler History
1. Open Task Scheduler (`taskschd.msc`)
2. Find "TutorDex-Aggregator" in Task Scheduler Library
3. Select → History tab → View all events

---

## Troubleshooting

### Task won't start on boot
- Ensure you ran `install_task_scheduler.ps1` as Administrator
- Check Task Scheduler logs for errors
- Verify Python is in your PATH

### Script crashes immediately
- Test manually first: `python runner.py start`
- Check `.env` file configuration
- Verify all dependencies installed: `pip install -r requirements.txt`

### Can't stop the task
```powershell
Stop-ScheduledTask -TaskName "TutorDex-Aggregator"
Get-Process python | Where-Object {$_.CommandLine -like "*runner.py*"} | Stop-Process -Force
```

### Python not found
Edit `start_tutordex_loop.bat` and replace `python` with the full path to your Python executable:
```batch
"C:\Users\Living Room\AppData\Local\Python\pythoncore-3.14-64\python.exe" runner.py start
```

---

## Files Created

- `start_tutordex.bat` - Simple one-time start script
- `start_tutordex_loop.bat` - Auto-restart wrapper (recommended)
- `install_task_scheduler.ps1` - Install as scheduled task
- `uninstall_task_scheduler.ps1` - Remove scheduled task
- `README_AUTOSTART.md` - This file

---

## Security Notes

⚠️ The scheduled task runs with your user permissions. Ensure:
- Your `.env` file is secure (contains API keys)
- File permissions are restricted to your user account
- The task runs only when you're logged in (or use Service mode)

---

## Need Help?

Check the main README.md or logs for more information.
