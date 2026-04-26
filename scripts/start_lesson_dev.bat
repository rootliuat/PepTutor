@echo off
setlocal

set "ROOT_DIR=%~dp0.."
for %%I in ("%ROOT_DIR%") do set "ROOT_DIR=%%~fI"

set "BACKEND_DIR=%ROOT_DIR%\backend\LightRAG"
set "FRONTEND_DIR=%ROOT_DIR%\frontend\airi"
set "BACKEND_HOST=127.0.0.1"
set "BACKEND_PORT=9625"
set "FRONTEND_PORT=5173"
set "SERVER_BIN=%BACKEND_DIR%\.venv\Scripts\lightrag-server.exe"

if not "%PEPTUTOR_LESSON_BACKEND_HOST%"=="" set "BACKEND_HOST=%PEPTUTOR_LESSON_BACKEND_HOST%"
if not "%PEPTUTOR_LESSON_BACKEND_PORT%"=="" set "BACKEND_PORT=%PEPTUTOR_LESSON_BACKEND_PORT%"
if not "%PEPTUTOR_LESSON_FRONTEND_PORT%"=="" set "FRONTEND_PORT=%PEPTUTOR_LESSON_FRONTEND_PORT%"
if not "%PEPTUTOR_LESSON_SERVER_BIN%"=="" set "SERVER_BIN=%PEPTUTOR_LESSON_SERVER_BIN%"

set "BACKEND_URL=http://%BACKEND_HOST%:%BACKEND_PORT%"

if not exist "%SERVER_BIN%" (
  echo Missing LightRAG server binary:
  echo   %SERVER_BIN%
  echo Install backend dependencies first:
  echo   cd backend\LightRAG
  echo   py -m venv .venv
  echo   .venv\Scripts\python -m pip install --no-build-isolation -e .[test]
  exit /b 1
)

where pnpm >nul 2>nul
if errorlevel 1 (
  echo Missing pnpm. Install frontend dependencies first in frontend\airi.
  exit /b 1
)

set "NO_PROXY=127.0.0.1,localhost,::1"
set "no_proxy=127.0.0.1,localhost,::1"
set "PEPTUTOR_LESSON_LIVE_PROMPTS=1"
set "PEPTUTOR_DEBUG_SIGNALS=1"

if /I not "%PEPTUTOR_LESSON_FULL_STACK%"=="1" (
  set "PEPTUTOR_LESSON_VECTOR_RETRIEVAL=0"
  set "PEPTUTOR_SIMPLEMEM_PROMPT_INJECTION=0"
  set "PEPTUTOR_SIMPLEMEM_WRITEBACK=0"
  set "PEPTUTOR_SIMPLEMEM_SEMANTIC_RECALL=0"
)

echo Starting PepTutor lesson backend: %BACKEND_URL%
start "PepTutor Lesson Backend" /D "%BACKEND_DIR%" cmd /k ""%SERVER_BIN%" --host %BACKEND_HOST% --port %BACKEND_PORT%"

echo Waiting for lesson backend...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(120); do { try { $r=Invoke-WebRequest -UseBasicParsing '%BACKEND_URL%/lesson/catalog' -TimeoutSec 5; if ($r.StatusCode -eq 200) { exit 0 } } catch { }; Start-Sleep -Seconds 1 } while ((Get-Date) -lt $deadline); exit 1"
if errorlevel 1 (
  echo Timed out waiting for lesson backend: %BACKEND_URL%/lesson/catalog
  exit /b 1
)

echo Starting AIRI stage-web frontend: http://127.0.0.1:%FRONTEND_PORT%/lesson
set "VITE_PEPTUTOR_LESSON_API_URL=%BACKEND_URL%"
set "VITE_PEPTUTOR_DEV_PROXY_TARGET=%BACKEND_URL%"
if "%VITE_PEPTUTOR_TTS_PROVIDER%"=="" if not "%PEPTUTOR_LESSON_TTS_PROVIDER%"=="" set "VITE_PEPTUTOR_TTS_PROVIDER=%PEPTUTOR_LESSON_TTS_PROVIDER%"
if "%VITE_PEPTUTOR_TTS_MODEL%"=="" if not "%PEPTUTOR_LESSON_TTS_MODEL%"=="" set "VITE_PEPTUTOR_TTS_MODEL=%PEPTUTOR_LESSON_TTS_MODEL%"
if "%VITE_PEPTUTOR_TTS_VOICE%"=="" if not "%PEPTUTOR_LESSON_TTS_VOICE%"=="" set "VITE_PEPTUTOR_TTS_VOICE=%PEPTUTOR_LESSON_TTS_VOICE%"
set "VITE_PEPTUTOR_SKIP_REMOTE_ASSET_DOWNLOADS=true"
start "PepTutor Lesson Frontend" /D "%FRONTEND_DIR%" cmd /k "pnpm -F @proj-airi/stage-web dev -- --host 0.0.0.0 --port %FRONTEND_PORT%"

echo.
echo Open: http://127.0.0.1:%FRONTEND_PORT%/lesson
echo Backend: %BACKEND_URL%
endlocal
