@echo off
setlocal enabledelayedexpansion

if not defined BACKEND_URL set "BACKEND_URL=http://127.0.0.1:8000"

set "SB_URL="
if defined SUPABASE_URL set "SB_URL=%SUPABASE_URL%"
if not defined SB_URL if defined SUPABASE_URL_HOST set "SB_URL=%SUPABASE_URL_HOST%"
if not defined SB_URL if defined SUPABASE_URL_DOCKER set "SB_URL=%SUPABASE_URL_DOCKER%"

set "SB_KEY="
if defined SUPABASE_SERVICE_ROLE_KEY set "SB_KEY=%SUPABASE_SERVICE_ROLE_KEY%"
if not defined SB_KEY if defined SUPABASE_KEY set "SB_KEY=%SUPABASE_KEY%"

echo TutorDex smoke test: backend
echo   BACKEND_URL=%BACKEND_URL%

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  set "PY=py -3"
) else (
  set "PY=python"
)

if not "%SB_URL%"=="" (
  if not "%SB_KEY%"=="" (
    echo   SUPABASE_URL=%SB_URL%
    %PY% scripts\smoke_test.py --backend-url "%BACKEND_URL%" --supabase-url "%SB_URL%" --supabase-key "%SB_KEY%"
  ) else (
    echo   SUPABASE_URL/SUPABASE_KEY not set; skipping direct Supabase RPC checks
    %PY% scripts\smoke_test.py --backend-url "%BACKEND_URL%" --skip-supabase-rpcs
  )
) else (
  echo   SUPABASE_URL/SUPABASE_KEY not set; skipping direct Supabase RPC checks
  %PY% scripts\smoke_test.py --backend-url "%BACKEND_URL%" --skip-supabase-rpcs
)

endlocal
exit /b %ERRORLEVEL%
