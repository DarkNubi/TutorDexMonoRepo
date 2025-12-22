@echo off
REM Auto-restart wrapper for TutorDex - keeps it running 24/7
cd /D d:\TutorDex\TutorDexAggregator

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
