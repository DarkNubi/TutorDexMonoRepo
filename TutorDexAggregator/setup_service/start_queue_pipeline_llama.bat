@echo off
REM Simplified queue pipeline entrypoint.
REM Prefer `python runner.py queue ...` which runs everything in ONE console.

setlocal enabledelayedexpansion
cd /D d:\TutorDex\TutorDexAggregator

if "%EXTRACT_WORKER_COUNT%"=="" set "EXTRACT_WORKER_COUNT=4"

REM Default LLM URL matches the default in extract_key_info.py/llm_client.py
if "%LLM_API_URL%"=="" set "LLM_API_URL=http://127.0.0.1:1234"

REM Backfill safety: don't broadcast/DM historical posts unless you explicitly override.
if "%EXTRACTION_WORKER_BROADCAST%"=="" set "EXTRACTION_WORKER_BROADCAST=0"
if "%EXTRACTION_WORKER_DMS%"=="" set "EXTRACTION_WORKER_DMS=0"

echo ========================================
echo Starting TutorDex Queue Pipeline (llama-server) at %date% %time%
echo - LLM_API_URL=%LLM_API_URL%
echo - EXTRACT_WORKER_COUNT=%EXTRACT_WORKER_COUNT%
echo - Broadcast=%EXTRACTION_WORKER_BROADCAST%  DMs=%EXTRACTION_WORKER_DMS%
echo - Nominatim enabled (DISABLE_NOMINATIM not set)
echo ========================================

where python >nul 2>&1
if %errorlevel% equ 0 (
  python runner.py queue --days 30 --workers %EXTRACT_WORKER_COUNT% --start-llama
) else (
  py -3 runner.py queue --days 30 --workers %EXTRACT_WORKER_COUNT% --start-llama
)
