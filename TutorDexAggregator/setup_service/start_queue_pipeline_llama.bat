@echo off
REM Simplified queue pipeline entrypoint (Windows host).
REM Starts llama-server (optional) and then starts the raw collector + queue worker loops.

setlocal enabledelayedexpansion
cd /D d:\TutorDex\TutorDexAggregator

REM Default LLM URL matches the default in extract_key_info.py
if "%LLM_API_URL%"=="" set "LLM_API_URL=http://127.0.0.1:1234"

REM Backfill safety: don't broadcast/DM historical posts unless you explicitly override.
if "%EXTRACTION_WORKER_BROADCAST%"=="" set "EXTRACTION_WORKER_BROADCAST=0"
if "%EXTRACTION_WORKER_DMS%"=="" set "EXTRACTION_WORKER_DMS=0"

echo ========================================
echo Starting TutorDex Queue Pipeline (llama-server) at %date% %time%
echo - LLM_API_URL=%LLM_API_URL%
echo - Broadcast=%EXTRACTION_WORKER_BROADCAST%  DMs=%EXTRACTION_WORKER_DMS%
echo ========================================

REM Optional: start llama-server in a separate console window (uses start_llama_server_loop.bat defaults/env vars).
if exist start_llama_server_loop.bat (
  start "TutorDex llama-server" cmd /c start_llama_server_loop.bat
)

REM Start the raw collector and queue worker in separate console windows.
start "TutorDex Collector" cmd /c setup_service\\start_collector_loop.bat
start "TutorDex Worker" cmd /c setup_service\\start_extract_worker_loop.bat
