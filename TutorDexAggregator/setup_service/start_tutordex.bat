@echo off
REM Batch script to run TutorDex runner with proper Python environment
cd /d "%~dp0\.."

REM Try to find Python in common locations
where python >nul 2>&1
if %errorlevel% equ 0 (
    python runner.py start
) else (
    py -3 runner.py start
)

REM If the script exits unexpectedly, wait before closing
if errorlevel 1 (
    echo.
    echo TutorDex exited with error code %errorlevel%
    pause
)
