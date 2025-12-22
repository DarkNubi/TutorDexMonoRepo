@echo off
REM Auto-restart wrapper for TutorDex - keeps it running 24/7
cd /D d:\TutorDex\TutorDexAggregator

REM If called as "collector" mode, run only the raw collector tail loop.
if /I "%~1"=="collector" goto collector_loop

REM Start the raw collector tail in a separate process/window (so LLM outages don't stop raw capture).
REM This launches this same .bat in "collector" mode and lets the main loop run runner.py as before.
start "TutorDex Raw Collector" /min cmd /c "\"%~f0\" collector"

:loop
echo ========================================
echo Starting TutorDex at %date% %time%
echo ========================================

REM Try to find Python in common locations
where python >nul 2>&1
if %errorlevel% equ 0 (
    python runner.py start
) else (
    py -3 runner.py start
)

echo.
echo ========================================
echo TutorDex stopped at %date% %time%
echo Restarting in 10 seconds...
echo Press Ctrl+C to stop auto-restart
echo ========================================
timeout /t 10 /nobreak
goto loop

:collector_loop
echo ========================================
echo Starting TutorDex Raw Collector at %date% %time%
echo ========================================

REM Try to find Python in common locations
where python >nul 2>&1
if %errorlevel% equ 0 (
    python collector.py tail
) else (
    py -3 collector.py tail
)

echo.
echo ========================================
echo Raw Collector stopped at %date% %time%
echo Restarting in 10 seconds...
echo Press Ctrl+C to stop auto-restart
echo ========================================
timeout /t 10 /nobreak
goto collector_loop
