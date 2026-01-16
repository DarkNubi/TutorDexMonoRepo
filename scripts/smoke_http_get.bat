@echo off
setlocal enabledelayedexpansion

if "%~1"=="" (
  echo Usage: %~nx0 URL [URL2 ...]
  exit /b 2
)

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  set "PY=py -3"
) else (
  set "PY=python"
)

%PY% scripts\smoke_http_get.py %*
exit /b %ERRORLEVEL%
