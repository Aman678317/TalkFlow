# TalkFlow Language Intelligence Agent (Agent 03)

Production-oriented AI Language Intelligence Agent in Python for the TalkFlow / GlobalTalk AI multilingual communication platform.

## Key Capabilities

- **Real-Time Multilingual Detection**: fastText `lid.176` direct C++ extension call (bypasses NumPy 2.x bugs, execution in $< 1.5$ ms).
- **Indic Disambiguation**: Deterministic distinction between Marathi (`mr`) and Hindi (`hi`) in Devanagari script using lexical markers.
- **Hinglish & Code-Switching**: Sub-sentence span segmentation with exact character offsets (`text_start_offset`, `text_end_offset`) and Agent 02 word timestamp alignment.
- **Multi-Source Evidence Fusion**: Weighted Bayesian scoring across Text LID (40%), STT Whisper hint (25%), Unicode Script (20%), and Speaker context (15%).
- **Stateful Speaker Tracking**: 10-utterance sliding window with hysteresis to suppress flip-flopping on isolated loanwords.
- **TalkFlow Capability Verification**: Real-time validation against TalkFlow's translation catalog (`production`, `experimental`, `unsupported`).
- **Fail-Closed Reporting**: Honest degradation on short/ambiguous text (`< 3` characters or confidence `< 0.45`), emitting `"und"` rather than fabricating guesses.
- **Operational Diagnostic Brain**: OpenAI Agents SDK / Ollama (`qwen3.5:4b`) running strictly out-of-band for diagnostic telemetry.

## Quick Start

```powershell
# Activate environment
cd "i:\vioces agent\language-intelligence-agent"
..\.venv\Scripts\Activate.ps1

# Start microservice
uvicorn app.main:app --host 127.0.0.1 --port 8003

# Run self-audit verification
python scripts/verify_agent.py

# Run unit & integration tests
pytest tests/ -v

# Run performance benchmark
python scripts/benchmark_detection.py
```

## Dashboard & Swagger Docs

- **Interactive Dashboard**: `http://127.0.0.1:8003/`
- **Swagger Documentation**: `http://127.0.0.1:8003/docs`
- **Health Check**: `http://127.0.0.1:8003/health`
- **Readiness Probe**: `http://127.0.0.1:8003/ready`
- **Prometheus Metrics**: `http://127.0.0.1:8003/metrics`

