@echo off
REM Auto-restart wrapper for the extraction worker (queue pipeline).
REM This script inherits env vars from the parent process.

cd /D d:\TutorDex\TutorDexAggregator

:loop
echo ========================================
echo Starting TutorDex Extract Worker at %date% %time%
echo - pipeline_version=%EXTRACTION_PIPELINE_VERSION%
echo - batch=%EXTRACTION_WORKER_BATCH% idle_s=%EXTRACTION_WORKER_IDLE_S%
echo - broadcast=%EXTRACTION_WORKER_BROADCAST% dms=%EXTRACTION_WORKER_DMS%
echo - llm_api_url=%LLM_API_URL%
echo ========================================

where python >nul 2>&1
if %errorlevel% equ 0 (
    python workers\\extract_worker.py
) else (
    py -3 workers\\extract_worker.py
)

echo.
echo Extract Worker stopped at %date% %time% - restarting in 5 seconds...
timeout /t 5 /nobreak >nul
goto loop

