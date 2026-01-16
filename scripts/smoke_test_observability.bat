@echo off
setlocal

if not defined PROMETHEUS_URL set "PROMETHEUS_URL=http://127.0.0.1:9090/-/ready"
if not defined ALERTMANAGER_URL set "ALERTMANAGER_URL=http://127.0.0.1:9093/-/ready"
if not defined GRAFANA_URL set "GRAFANA_URL=http://127.0.0.1:3300/api/health"

echo TutorDex smoke test: observability
echo   PROMETHEUS_URL=%PROMETHEUS_URL%
echo   ALERTMANAGER_URL=%ALERTMANAGER_URL%
echo   GRAFANA_URL=%GRAFANA_URL%

call scripts\smoke_http_get.bat "%PROMETHEUS_URL%" "%ALERTMANAGER_URL%" "%GRAFANA_URL%"
exit /b %ERRORLEVEL%

