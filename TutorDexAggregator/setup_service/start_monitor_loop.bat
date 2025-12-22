@echo off
REM Auto-restart wrapper for TutorDex Monitor (alerts + daily summary)
cd /D d:\TutorDex\TutorDexAggregator

:loop
echo ========================================
echo Starting TutorDex Monitor at %date% %time%
echo ========================================

REM Try to find Python in common locations
where python >nul 2>&1
if %errorlevel% equ 0 (
    python monitoring\monitor.py
) else (
    py -3 monitoring\monitor.py
)

echo.
echo ========================================
echo TutorDex Monitor stopped at %date% %time%
echo Restarting in 10 seconds...
echo Press Ctrl+C to stop auto-restart
echo ========================================
timeout /t 10 /nobreak
goto loop

