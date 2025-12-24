@echo off
REM Auto-restart wrapper for the raw collector tail loop.

cd /D d:\TutorDex\TutorDexAggregator

:loop
echo ========================================
echo Starting TutorDex Raw Collector (tail) at %date% %time%
echo - extraction_queue_enabled=%EXTRACTION_QUEUE_ENABLED%
echo - pipeline_version=%EXTRACTION_PIPELINE_VERSION%
echo ========================================

where python >nul 2>&1
if %errorlevel% equ 0 (
    python collector.py tail
) else (
    py -3 collector.py tail
)

echo.
echo Raw Collector stopped at %date% %time% - restarting in 10 seconds...
timeout /t 10 /nobreak >nul
goto loop

