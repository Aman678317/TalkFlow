@echo off
title GlobalTalk AI - Full-Stack Launcher (API + Web)
color 0B
echo ======================================================================
echo          GlobalTalk AI - Full-Stack Application Launcher
echo ======================================================================
echo.
cd /d "%~dp0"

echo [1/2] Launching GlobalTalk AI Backend on http://127.0.0.1:8088 ...
start "GlobalTalk AI Backend (8088)" cmd /k "python run_api.py"

timeout /t 2 /nobreak >nul

echo [2/2] Launching Web Frontend on http://localhost:5173 ...
start "GlobalTalk AI Web (5173)" cmd /k "cd apps\web && npx vite"

echo.
echo ======================================================================
echo GlobalTalk AI is running!
echo - Web Application:  http://localhost:5173
echo - API Documentation: http://127.0.0.1:8088/api/docs
echo - DeepL Translator: http://localhost:5173/translate
echo - DeepL Write:      http://localhost:5173/write
echo - DeepL Voice:      http://localhost:5173/voice
echo - Video Meetings:   http://localhost:5173/meetings
echo ======================================================================
echo.
pause
