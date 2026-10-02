@echo off
title GlobalTalk AI - Create Full-Stack ZIP Archive
color 0A
cd /d "%~dp0"

echo ======================================================================
echo           GlobalTalk AI - Packaging Full-Stack Application
echo ======================================================================
echo.
echo Packaging backend, web frontend, config, and assets...
echo (Excluding node_modules, .git, and cache directories)
echo.

python make_zip.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Python packaging failed or Python was not found in PATH.
    echo [!] Trying PowerShell fallback...
    powershell -NoProfile -Command "Compress-Archive -Path apps,services,ai,docs,tests,package.json,README.md,run_api.py,START_ALL.bat -DestinationPath globaltalk-ai-fullstack.zip -Force"
    echo Done! Created globaltalk-ai-fullstack.zip
)

echo.
pause
