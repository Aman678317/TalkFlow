@echo off
title TalkFlow Full-Stack AI Platform (7 Agents + Orchestrator + WebRTC Gateway)
color 0B
echo ======================================================================
echo       TalkFlow AI — Full Multilingual Video Translation Platform
echo ======================================================================
echo.

cd /d "%~dp0"

echo [1/5] Checking Ollama daemon...
start "Ollama Engine" cmd /k "ollama serve"
timeout /t 2 /nobreak >nul

echo [2/5] Launching 7-Agent Autonomous Translation Cluster...
start "Agent 01 - Audio Intelligence (8001)" cmd /k "cd services\agents\audio-intelligence-agent && python -m uvicorn app.main:app --host 127.0.0.1 --port 8001"
start "Agent 02 - Speech Recognition (8002)" cmd /k "cd services\agents\speech-recognition-agent && python -m uvicorn app.main:app --host 127.0.0.1 --port 8002"
start "Agent 03 - Language Intelligence (8003)" cmd /k "cd services\agents\language-intelligence-agent && python -m uvicorn app.main:app --host 127.0.0.1 --port 8003"
start "Agent 04 - Neural Translation (8004)" cmd /k "cd services\agents\neural-translation-agent && python -m uvicorn app.main:app --host 127.0.0.1 --port 8004"
start "Agent 05 - Quality Evaluation (8005)" cmd /k "cd services\agents\translation-quality-agent && python -m uvicorn app.main:app --host 127.0.0.1 --port 8005"
start "Agent 06 - Voice Generation (8006)" cmd /k "cd services\agents\voice-generation-agent && python -m uvicorn app.main:app --host 127.0.0.1 --port 8006"
start "Agent 07 - Audio Delivery (8007)" cmd /k "cd services\agents\audio-delivery-agent && python -m uvicorn app.main:app --host 127.0.0.1 --port 8007"

timeout /t 3 /nobreak >nul

echo [3/5] Launching Central Orchestrator & Fanout Gateway on port 8000...
start "TalkFlow Orchestrator (8000)" cmd /k "cd services\orchestrator && python -m uvicorn service:app --host 127.0.0.1 --port 8000"

echo [4/5] Launching TalkFlow WebRTC Backend on port 8088...
start "TalkFlow API (8088)" cmd /k "python run_api.py"

timeout /t 2 /nobreak >nul

echo [5/5] Launching TalkFlow Web Application on http://localhost:5173 ...
start "TalkFlow Web (5173)" cmd /k "cd apps\web && npm run dev"

echo.
echo ======================================================================
echo TalkFlow AI Platform is Running!
echo - Web Meetings:       http://localhost:5173/meetings
echo - Main Web App:       http://localhost:5173
echo - Central API Docs:   http://127.0.0.1:8088/api/docs
echo - Orchestrator Docs:  http://127.0.0.1:8000/docs
echo ======================================================================
echo.
pause

