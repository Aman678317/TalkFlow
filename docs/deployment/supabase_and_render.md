# Connecting GlobalTalk AI with Supabase & Render

This guide outlines how GlobalTalk AI's backend connects with **Supabase** (PostgreSQL database & pooler) and deploys automatically on **Render** (FastAPI Web Service + WebSockets).

---

## 1. Supabase Setup

### A. Get Your Connection String
1. In your **Supabase Dashboard**, open your project.
2. Navigate to **Project Settings** -> **Database**.
3. Under **Connection string**, select **URI**:
   - **Transaction Pooler (Port 6543) [RECOMMENDED for Render & Serverless]**:
     ```
     postgresql://postgres.[YOUR-PROJECT-REF]:[YOUR-PASSWORD]@aws-0-[REGION].pooler.supabase.com:6543/postgres?sslmode=require
     ```
   - **Direct Connection (Port 5432)**:
     ```
     postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres?sslmode=require
     ```

### B. Built-in Compatibility Handled by GlobalTalk AI
In `services/api/app/db/session.py`:
- `postgres://` is automatically converted to `postgresql+asyncpg://`.
- `sslmode=require` is safely translated to asyncpg SSL parameters to prevent `TypeError: connect() got an unexpected keyword argument 'sslmode'`.
- Port 6543 / Supabase pooler connections automatically have `statement_cache_size: 0` and `prepared_statement_cache_size: 0` enabled so transaction pooling with pgBouncer works without prepared statement conflicts.

---

## 2. Render Deployment (`render.yaml`)

A root [`render.yaml`](../../render.yaml) Blueprint is provided in this repository.

### A. Automatic Blueprint Deployment
1. Go to your [Render Dashboard](https://dashboard.render.com/).
2. Click **New +** -> **Blueprint**.
3. Connect your GitHub repository (`TalkFlow` or `globaltalk-ai`).
4. Select the active branch: `fix/vercel-deployment-500`.
5. Render will automatically detect `render.yaml` and configure:
   - **Service Name**: `globaltalk-api`
   - **Type**: Web Service
   - **Runtime**: Python 3.11.9
   - **Root Directory**: `services/api`
   - **Build Command**: `pip install --upgrade pip && pip install -r requirements.txt`
   - **Start Command**: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2`
   - **Health Check Path**: `/health`
   - **Auto-Deploy**: Enabled on Git push.

### B. Configure Environment Variables in Render
Under the `globaltalk-api` Environment tab on Render, fill in:
| Variable | Value |
|---|---|
| `DATABASE_URL` | Your Supabase connection string (from Step 1) |
| `SUPABASE_URL` | `https://[YOUR-PROJECT-REF].supabase.co` |
| `SUPABASE_ANON_KEY` | Your Supabase Anon Key (from Project Settings -> API) |
| `SUPABASE_SERVICE_ROLE_KEY` | Optional (for admin service operations) |
| `CORS_ORIGINS` | `https://globaltalk-ai.vercel.app,http://localhost:5173` |
| `JWT_SECRET` | Auto-generated or custom 32+ character secret |
| `TRANSLATION_PROVIDER` | `auto` (or `neural_online`, `deepl`, etc.) |
| `STT_PROVIDER` | `auto` (or `faster_whisper`, `stt_http`, etc.) |
| `TTS_PROVIDER` | `auto` (or `kokoro`, `piper`, `tts_http`, etc.) |

---

## 3. Real-Time Multilingual Translation Pipeline

The live audio translation pipeline works out of the box:
- **Audio Capture**: Microphone captured at 16 kHz PCM16 frames via Web Audio API / AudioWorklet.
- **Voice Activity Detection**: Low-latency `EnergyVAD` detects speech boundaries without burning GPU/CPU on silence.
- **Speech Recognition**: Incremental partial transcripts emitted during speech; final canonical transcript committed on speech completion.
- **Translation Fan-Out**: Translates directly from canonical source text into each listener's configured preferred language (`en`, `hi`, `es`, `fr`, etc.).
- **Speech Synthesis (TTS)**: Synthesizes translated audio stream and delivers binary audio frames (`0x54` header) and `tts.chunk` events directly to the remote participant.
- **Audio Playback**: The listener's browser queues and plays back the translated speech without echo or double-playback.
