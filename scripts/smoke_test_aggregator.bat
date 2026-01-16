@echo off
setlocal

if not defined BACKEND_URL set "BACKEND_URL=http://127.0.0.1:8000"

rem Prefer going through backend, since worker/collector health ports are not published by default in docker-compose.
if not defined AGG_WORKER_HEALTH_URL set "AGG_WORKER_HEALTH_URL=%BACKEND_URL%/health/worker"
if not defined AGG_COLLECTOR_HEALTH_URL set "AGG_COLLECTOR_HEALTH_URL=%BACKEND_URL%/health/collector"

echo TutorDex smoke test: aggregator (worker/collector via backend health)
echo   BACKEND_URL=%BACKEND_URL%
echo   AGG_WORKER_HEALTH_URL=%AGG_WORKER_HEALTH_URL%
echo   AGG_COLLECTOR_HEALTH_URL=%AGG_COLLECTOR_HEALTH_URL%

call scripts\smoke_http_get.bat "%AGG_WORKER_HEALTH_URL%" "%AGG_COLLECTOR_HEALTH_URL%"
exit /b %ERRORLEVEL%
