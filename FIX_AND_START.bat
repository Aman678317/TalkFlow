@echo off
title GlobalTalk AI - Backend Launcher
color 0B
echo ======================================================================
echo                     GlobalTalk AI - Backend Launcher
echo ======================================================================
echo.

cd /d "%~dp0"

echo [1/3] Detecting Python...
set PYCMD=
where python >nul 2>&1 && set PYCMD=python
if "%PYCMD%"=="" (
    where py >nul 2>&1 && set PYCMD=py -3
)
if "%PYCMD%"=="" (
    where python3 >nul 2>&1 && set PYCMD=python3
)

if "%PYCMD%"=="" (
    echo [ERROR] Python was not found in PATH!
    echo Please install Python 3.11+ from https://python.org or add it to PATH.
    pause
    exit /b 1
)

echo Found Python: %PYCMD%

echo.
echo [2/3] Checking current API dependencies...
%PYCMD% -c "import uvicorn, fastapi, sqlalchemy, pydantic_settings, jwt, bcrypt, email_validator, livekit.api" >nul 2>&1
if errorlevel 1 goto install_api_dependencies
echo Dependencies are ready.
goto api_dependencies_ready

:install_api_dependencies
echo Dependencies are missing. Installing now (this may take a minute)...
%PYCMD% -m pip install -r apps\api\requirements.txt
if errorlevel 1 exit /b 1

:api_dependencies_ready

echo.
if "%API_PORT%"=="" set "API_PORT=8000"
set "PYTHONPATH=%~dp0apps\api;%~dp0"
if defined LIVEKIT_URL goto start_api
docker info >nul 2>&1
if errorlevel 1 goto video_unavailable
echo Starting the local LiveKit video room...
docker compose up -d livekit
if errorlevel 1 goto video_unavailable
set "LIVEKIT_URL=ws://localhost:7880"
set "LIVEKIT_PUBLIC_URL=ws://localhost:7880"
set "LIVEKIT_API_KEY=devkey"
set "LIVEKIT_API_SECRET=devsecret-at-least-32-chars-long!!"
echo Local video and room audio are enabled.
goto start_api

:video_unavailable
echo Docker LiveKit is unavailable. Audio translation will work; video needs LiveKit.

:start_api
echo [3/3] Starting backend on http://127.0.0.1:%API_PORT% ...
echo API Docs: http://127.0.0.1:%API_PORT%/docs
echo Web App:  http://localhost:5173
echo.
%PYCMD% -m uvicorn globaltalk.main:app --host 127.0.0.1 --port %API_PORT% --reload

if errorlevel 1 echo [ERROR] Server stopped with error code %ERRORLEVEL%.
if errorlevel 1 pause
