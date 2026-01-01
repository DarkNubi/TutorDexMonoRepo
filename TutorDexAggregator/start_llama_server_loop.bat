@echo off
REM Auto-restart wrapper for llama.cpp `llama-server` (OpenAI-compatible).
REM Expects you to set LLAMA_SERVER_EXE and LLAMA_MODEL_PATH (either in this file or as user/system env vars).
REM
REM Recommended:
REM - Keep port at 1234 so TutorDexAggregator's default LLM_API_URL works unchanged.
REM - Keep ctx at 16384 to match your current LM Studio setup.
REM
REM Example (edit to your actual paths):
REM set "LLAMA_SERVER_EXE=C:\llama-bin\llama-server.exe"
REM set "LLAMA_MODEL_PATH=D:\models\liquidai-lfm2-8b-a1b.Q4_K_M.gguf"
REM
REM Optional overrides:
REM set "LLAMA_SERVER_HOST=0.0.0.0"
REM set "LLAMA_SERVER_PORT=1234"
REM set "LLAMA_CTX=16384"
REM set "LLAMA_THREADS=6"
REM set "LLAMA_BATCH=512"
REM set "LLAMA_NGL=999"
REM set "LLAMA_SERVER_ARGS=--log-format text"

setlocal enabledelayedexpansion
cd /D d:\TutorDex\TutorDexAggregator

REM Local defaults (safe to override via env vars).
if "%LLAMA_SERVER_EXE%"=="" set "LLAMA_SERVER_EXE=C:\llama-bin\llama-server.exe"
if "%LLAMA_MODEL_PATH%"=="" set "LLAMA_MODEL_PATH=C:\models\LFM2-8B-A1B-Q4_K_M.gguf"

if "%LLAMA_SERVER_EXE%"=="" (
  echo [ERROR] LLAMA_SERVER_EXE is not set.
  echo Set it to the full path of llama-server.exe and re-run.
  pause
  exit /b 2
)
if "%LLAMA_MODEL_PATH%"=="" (
  echo [ERROR] LLAMA_MODEL_PATH is not set.
  echo Set it to the full path of your GGUF model and re-run.
  pause
  exit /b 2
)

REM Bind to 0.0.0.0 by default so WSL/containers can reach the server.
if "%LLAMA_SERVER_HOST%"=="" set "LLAMA_SERVER_HOST=0.0.0.0"
if "%LLAMA_SERVER_PORT%"=="" set "LLAMA_SERVER_PORT=1234"
if "%LLAMA_CTX%"=="" set "LLAMA_CTX=16384"
if "%LLAMA_THREADS%"=="" set "LLAMA_THREADS=6"
if "%LLAMA_BATCH%"=="" set "LLAMA_BATCH=512"
if "%LLAMA_NGL%"=="" set "LLAMA_NGL=999"
REM Default: force single slot and KV offload unless explicitly overridden.
if "%LLAMA_SERVER_ARGS%"=="" set "LLAMA_SERVER_ARGS=-np 1"


:loop
echo ========================================
echo Starting llama-server at %date% %time%
echo - exe:  %LLAMA_SERVER_EXE%
echo - model:%LLAMA_MODEL_PATH%
echo - host: %LLAMA_SERVER_HOST%  port: %LLAMA_SERVER_PORT%
echo - ctx:  %LLAMA_CTX%  threads: %LLAMA_THREADS%  batch: %LLAMA_BATCH%  ngl: %LLAMA_NGL%
echo ========================================

REM Keep flags conservative for compatibility across llama.cpp versions.
REM Add any version-specific flags via LLAMA_SERVER_ARGS.
"%LLAMA_SERVER_EXE%" ^
  -m "%LLAMA_MODEL_PATH%" ^
  --host %LLAMA_SERVER_HOST% --port %LLAMA_SERVER_PORT% ^
  -c %LLAMA_CTX% -t %LLAMA_THREADS% -b %LLAMA_BATCH% -ngl %LLAMA_NGL% ^
  %LLAMA_SERVER_ARGS%

echo.
echo llama-server stopped at %date% %time% - restarting in 5 seconds...
timeout /t 5 /nobreak >nul
goto loop
