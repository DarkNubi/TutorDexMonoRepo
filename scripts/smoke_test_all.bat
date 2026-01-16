@echo off
setlocal enabledelayedexpansion

set "failed=0"

echo ==^> backend
call scripts\smoke_test_backend.bat
if errorlevel 1 (
  set /a failed+=1
  echo FAIL: backend
) else (
  echo PASS: backend
)

echo.
echo ==^> aggregator
call scripts\smoke_test_aggregator.bat
if errorlevel 1 (
  set /a failed+=1
  echo FAIL: aggregator
) else (
  echo PASS: aggregator
)

echo.
echo ==^> observability
call scripts\smoke_test_observability.bat
if errorlevel 1 (
  set /a failed+=1
  echo FAIL: observability
) else (
  echo PASS: observability
)

echo.
if not "!failed!"=="0" (
  echo Smoke tests failed: !failed!
  exit /b 1
)
echo All smoke tests passed
exit /b 0

