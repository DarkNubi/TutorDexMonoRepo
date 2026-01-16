@echo off
setlocal

echo TutorDex smoke test: integration
echo   Running backend smoke test...
call scripts\smoke_test_backend.bat
if errorlevel 1 exit /b %ERRORLEVEL%

echo.
echo   Running aggregator smoke test...
call scripts\smoke_test_aggregator.bat
exit /b %ERRORLEVEL%

