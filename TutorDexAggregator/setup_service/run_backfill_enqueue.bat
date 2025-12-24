@echo off
REM One-shot backfill runner that enqueues extraction jobs into Supabase.
REM Usage examples:
REM   run_backfill_enqueue.bat --since 2025-01-01T00:00:00+00:00 --max-messages 200
REM   run_backfill_enqueue.bat --channels t.me/FTassignments --since 2025-01-01T00:00:00+00:00

cd /D d:\TutorDex\TutorDexAggregator

REM Ensure enqueue is enabled (collector.py defaults to enabled, but allow explicit override).
if "%EXTRACTION_QUEUE_ENABLED%"=="" set "EXTRACTION_QUEUE_ENABLED=1"

where python >nul 2>&1
if %errorlevel% equ 0 (
    python collector.py backfill %*
) else (
    py -3 collector.py backfill %*
)

