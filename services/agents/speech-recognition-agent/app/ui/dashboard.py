"""Interactive Control Dashboard and Audio Playground for TalkFlow Speech Recognition Agent."""

FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <rect width="64" height="64" rx="14" fill="#0f172a"/>
  <path d="M16 32h6M26 22v20M36 14v36M46 24v16M56 32h-6" stroke="#10b981" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="36" cy="32" r="3" fill="#10b981"/>
</svg>"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TalkFlow — Speech Recognition Agent (Agent 02)</title>
  <link rel="icon" type="image/svg+xml" href="/favicon.ico">
  <style>
    :root {
      --bg: #0b0f19;
      --card-bg: #111827;
      --card-border: #1f2937;
      --accent: #10b981;
      --accent-glow: rgba(16, 185, 129, 0.25);
      --primary: #38bdf8;
      --text: #f9fafb;
      --text-muted: #9ca3af;
      --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.5;
      padding: 24px;
      min-height: 100vh;
    }
    .container { max-width: 1200px; margin: 0 auto; }
    header {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      padding-bottom: 24px;
      border-bottom: 1px solid var(--card-border);
      margin-bottom: 24px;
    }
    .brand { display: flex; align-items: center; gap: 14px; }
    .brand-icon {
      width: 44px;
      height: 44px;
      background: linear-gradient(135deg, #059669, #10b981);
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 0 16px var(--accent-glow);
    }
    .brand-icon svg { width: 26px; height: 26px; fill: none; stroke: #fff; stroke-width: 2.2; stroke-linecap: round; }
    .brand-title h1 { font-size: 20px; font-weight: 700; color: #fff; }
    .brand-title p { font-size: 13px; color: var(--text-muted); }
    .header-actions { display: flex; align-items: center; gap: 10px; }
    .status-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.3);
      padding: 6px 14px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 600;
    }
    .status-dot {
      width: 8px; height: 8px; background: #10b981; border-radius: 50%;
      box-shadow: 0 0 8px #10b981; animation: pulse 2s infinite;
    }
    @keyframes pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.4; transform: scale(0.85); } }
    .btn-link {
      background: #1f2937; color: var(--text); border: 1px solid #374151;
      padding: 7px 12px; border-radius: 6px; font-size: 12px; font-weight: 500;
      text-decoration: none; transition: all 0.2s;
    }
    .btn-link:hover { background: #374151; color: var(--accent); }
    
    .diagnostic-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }
    .card {
      background: var(--card-bg); border: 1px solid var(--card-border);
      border-radius: 12px; padding: 18px;
    }
    .card-label {
      font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em;
      color: var(--text-muted); font-weight: 600; margin-bottom: 6px;
    }
    .card-value { font-size: 17px; font-weight: 700; color: #fff; }
    .card-meta { font-size: 12px; color: var(--text-muted); margin-top: 4px; }

    .section-box {
      background: var(--card-bg); border: 1px solid var(--card-border);
      border-radius: 12px; padding: 24px; margin-bottom: 24px;
    }
    .tabs { display: flex; gap: 10px; border-bottom: 1px solid var(--card-border); padding-bottom: 12px; margin-bottom: 20px; }
    .tab-btn {
      background: transparent; border: none; color: var(--text-muted); font-size: 14px;
      font-weight: 600; padding: 8px 16px; border-radius: 6px; cursor: pointer; transition: all 0.2s;
    }
    .tab-btn.active { background: #1e293b; color: var(--accent); border: 1px solid rgba(16, 185, 129, 0.3); }
    .tab-content { display: none; }
    .tab-content.active { display: block; }

    .upload-zone {
      border: 2px dashed #374151; border-radius: 10px; padding: 32px; text-align: center;
      background: rgba(15, 23, 42, 0.4); cursor: pointer; margin-bottom: 16px;
    }
    .upload-zone:hover { border-color: var(--accent); }
    .file-input { display: none; }
    .primary-btn {
      background: linear-gradient(135deg, #059669, #10b981); color: #fff; border: none;
      padding: 10px 20px; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer;
    }
    .primary-btn:hover { opacity: 0.9; }
    .primary-btn:disabled { opacity: 0.5; cursor: not-allowed; }
    .stop-btn { background: #dc2626 !important; }

    .results-area { margin-top: 20px; display: none; }
    .transcript-box {
      background: #030712; border: 1px solid var(--card-border); border-radius: 8px;
      padding: 18px; margin-bottom: 16px; font-size: 16px; color: #f3f4f6; line-height: 1.6;
    }
    .badge {
      display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 600;
      background: rgba(16, 185, 129, 0.2); color: #34d399; margin-right: 8px;
    }

    .words-table {
      width: 100%; border-collapse: collapse; font-size: 12px; font-family: var(--font-mono);
      margin-top: 12px; background: #030712; border-radius: 6px; overflow: hidden;
    }
    .words-table th, .words-table td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #1f2937; }
    .words-table th { background: #111827; color: var(--text-muted); }

    .log-terminal {
      background: #030712; border: 1px solid #1f2937; border-radius: 8px;
      padding: 14px; height: 260px; overflow-y: auto; font-family: var(--font-mono); font-size: 12px;
    }
    .live-caption-box {
      background: #0f172a; border: 1px solid #38bdf8; border-radius: 8px;
      padding: 16px; margin-bottom: 14px; min-height: 70px; font-size: 15px; color: #38bdf8;
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="brand">
        <div class="brand-icon">
          <svg viewBox="0 0 24 24"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" x2="12" y1="19" y2="22"/></svg>
        </div>
        <div class="brand-title">
          <h1>TalkFlow Speech Recognition Agent (Agent 02)</h1>
          <p>Real-Time Multilingual STT, Hinglish Code-Switching & Streaming Captions</p>
        </div>
      </div>
      <div class="header-actions">
        <div class="status-badge"><div class="status-dot"></div><span>ONLINE</span></div>
        <a href="/docs" target="_blank" class="btn-link">Swagger Docs</a>
        <a href="/ready" target="_blank" class="btn-link">Readiness</a>
        <a href="/health" target="_blank" class="btn-link">Health</a>
        <a href="/metrics" target="_blank" class="btn-link">Metrics</a>
      </div>
    </header>

    <div class="diagnostic-grid">
      <div class="card">
        <div class="card-label">Primary STT Provider</div>
        <div class="card-value" id="diag-provider">faster-whisper</div>
        <div class="card-meta">CTranslate2 INT8 Precision</div>
      </div>
      <div class="card">
        <div class="card-label">Loaded Model Size</div>
        <div class="card-value" id="diag-model">whisper-base</div>
        <div class="card-meta">74M parameters / 4 CPU threads</div>
      </div>
      <div class="card">
        <div class="card-label">Canonical Audio Spec</div>
        <div class="card-value">16 kHz / Mono PCM16</div>
        <div class="card-meta">Direct Ingestion from Agent 01</div>
      </div>
      <div class="card">
        <div class="card-label">Operational Reasoning</div>
        <div class="card-value" id="diag-brain">OpenAI Agents SDK</div>
        <div class="card-meta">Ollama (qwen3.5:4b)</div>
      </div>
    </div>

    <div class="section-box">
      <div class="tabs">
        <button class="tab-btn active" onclick="switchTab('upload')">WAV File Recognition</button>
        <button class="tab-btn" onclick="switchTab('stream')">Live Microphone Streaming (WebSocket)</button>
        <button class="tab-btn" onclick="switchTab('languages')">Language Capabilities & Hinglish</button>
      </div>

      <!-- Tab 1: File Upload -->
      <div id="tab-upload" class="tab-content active">
        <p style="color: var(--text-muted); font-size: 13px; margin-bottom: 16px;">
          Upload an audio file (WAV, MP3, M4A, FLAC, etc. in English, Hindi, Marathi, Hinglish, etc.). The agent transcribes spoken words, extracts language hints, generates word-level timestamps, and suppresses acoustic hallucinations.
        </p>

        <div class="upload-zone" onclick="document.getElementById('audio-file-input').click()">
          <svg style="width: 38px; height: 38px; stroke: #10b981; fill: none; margin-bottom: 8px;" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" x2="12" y1="3" y2="15"/></svg>
          <div style="font-weight: 600; font-size: 14px;" id="file-label">Click to select or drag an audio file (WAV, MP3, etc.)</div>
          <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">Supports English, Indian languages, and mixed code-switching</div>
          <input type="file" id="audio-file-input" class="file-input" accept=".wav,.mp3,.m4a,.aac,.flac,.ogg,audio/*" onchange="handleFileSelected(this)">
        </div>

        <div style="display: flex; gap: 10px; align-items: center;">
          <button class="primary-btn" id="btn-transcribe" onclick="uploadAudioFile()" disabled>Transcribe Speech</button>
          <button class="primary-btn" id="btn-load-dhun" style="background: rgba(16, 185, 129, 0.15); border: 1px solid var(--accent); color: var(--accent);" onclick="loadDhunSample()">🎵 Load Full 4.3-Min Dhun Audio</button>
        </div>

        <div id="results-area" class="results-area">
          <div style="margin-bottom: 12px; display: flex; flex-wrap: wrap; gap: 8px;">
            <span class="badge" id="res-lang">LANG: EN</span>
            <span class="badge" id="res-conf">CONFIDENCE: 98%</span>
            <span class="badge" id="res-duration" style="background: rgba(168, 85, 247, 0.2); color: #c084fc;">DURATION: 0s</span>
            <span class="badge" id="res-words-count" style="background: rgba(34, 197, 94, 0.2); color: #4ade80;">WORDS: 0</span>
            <span class="badge" id="res-segments-count" style="background: rgba(251, 146, 60, 0.2); color: #fb923c;">SEGMENTS: 0</span>
            <span class="badge" id="res-latency" style="background: rgba(56, 189, 248, 0.2); color: #38bdf8;">LATENCY: 250ms</span>
          </div>

          <audio id="audio-preview" controls style="width: 100%; margin: 8px 0 16px 0; outline: none; border-radius: 8px; background: #030712; display: none;"></audio>

          <div class="transcript-box" id="res-transcript"></div>

          <h3 style="font-size: 13px; margin-bottom: 8px; color: var(--accent);">Word-Level Alignment & Timestamps (<span id="words-header-count">0</span> words):</h3>
          <div style="max-height: 380px; overflow-y: auto; border: 1px solid #1f2937; border-radius: 8px;">
            <table class="words-table" id="words-table" style="margin-top: 0;">
              <thead>
                <tr><th>Word</th><th>Start (s)</th><th>End (s)</th><th>Confidence</th></tr>
              </thead>
              <tbody id="words-body"></tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Tab 2: Live Streaming -->
      <div id="tab-stream" class="tab-content">
        <p style="color: var(--text-muted); font-size: 13px; margin-bottom: 16px;">
          Real-time speech recognition directly from your browser microphone. Emits streaming partial updates every 500ms and commits final transcripts on speech pauses.
        </p>

        <button class="primary-btn" id="btn-mic" onclick="toggleMicrophone()">Start Live Recognition</button>

        <div style="margin-top: 16px;">
          <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 6px;">Live Partial Transcription:</div>
          <div class="live-caption-box" id="live-partial">Waiting for speech...</div>
        </div>

        <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 6px;">Finalized Transcript Events:</div>
        <div class="log-terminal" id="stream-log"></div>
      </div>

      <!-- Tab 3: Language Capabilities -->
      <div id="tab-languages" class="tab-content">
        <h3 style="font-size: 15px; margin-bottom: 10px; color: var(--accent);">Indian Languages & Multilingual Coverage</h3>
        <p style="color: var(--text-muted); font-size: 13px; margin-bottom: 16px;">
          Agent 02 preserves the speaker's original language and code-switching without forcing unwanted translation.
        </p>
        <div id="lang-cards-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px;"></div>
      </div>
    </div>
  </div>

  <script>
    let selectedFile = null;
    let ws = null;
    let audioContext = null;
    let mediaStream = null;
    let scriptProcessor = null;
    let isStreaming = false;

    async function loadInfo() {
      try {
        const res = await fetch('/api/v1/agent/info');
        if (res.ok) {
          const d = await res.json();
          document.getElementById('diag-provider').innerText = d.provider;
          document.getElementById('diag-model').innerText = d.model;
        }

        const lres = await fetch('/api/v1/stt/languages');
        if (lres.ok) {
          const langs = await lres.json();
          const grid = document.getElementById('lang-cards-grid');
          grid.innerHTML = '';
          langs.forEach(l => {
            const c = document.createElement('div');
            c.className = 'card';
            c.innerHTML = `
              <div style="font-weight: 700; color: #fff;">${l.name} (${l.code.toUpperCase()})</div>
              <div style="font-size: 11px; color: var(--accent); margin-top: 2px;">${l.evaluation_status}</div>
              <div style="font-size: 11px; color: var(--text-muted); margin-top: 4px;">Code-Switching: ${l.code_switch_supported ? 'Supported' : 'Limited'}</div>
            `;
            grid.appendChild(c);
          });
        }
      } catch(e) {}
    }
    loadInfo();

    function switchTab(t) {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      event.target.classList.add('active');
      document.getElementById('tab-' + t).classList.add('active');
    }

    function handleFileSelected(input) {
      if (input.files && input.files[0]) {
        selectedFile = input.files[0];
        document.getElementById('file-label').innerText = `${selectedFile.name} (${(selectedFile.size / 1024).toFixed(1)} KB)`;
        document.getElementById('btn-transcribe').removeAttribute('disabled');
      }
    }

    async function loadDhunSample() {
      const btn = document.getElementById('btn-load-dhun');
      btn.innerText = "Loading Audio File...";
      try {
        const resp = await fetch('/api/v1/sample-audio/dhun');
        const blob = await resp.blob();
        selectedFile = new File([blob], 'kalsstockmedia-free-soul-shri-ram-jai-ram-jai-jai-ram-dhun-385110.mp3', { type: 'audio/mpeg' });
        document.getElementById('file-label').innerText = `${selectedFile.name} (${(selectedFile.size / 1024).toFixed(1)} KB)`;
        document.getElementById('btn-transcribe').removeAttribute('disabled');
        btn.innerText = "🎵 Loaded (Click Transcribe)";
      } catch (e) {
        alert("Failed to load sample: " + e.message);
        btn.innerText = "🎵 Load Full 4.3-Min Dhun Audio";
      }
    }

    async function uploadAudioFile() {
      if (!selectedFile) return;
      const btn = document.getElementById('btn-transcribe');
      btn.setAttribute('disabled', 'true');
      btn.innerText = "Transcribing Speech (Processing Audio)...";

      // Clear previous results while new file is processing
      document.getElementById('results-area').style.display = 'none';
      document.getElementById('res-transcript').innerText = '';
      document.getElementById('words-body').innerHTML = '';

      const fd = new FormData();
      fd.append("file", selectedFile);

      try {
        const resp = await fetch('/api/v1/stt/transcribe', { method: 'POST', body: fd });
        if (!resp.ok) {
          let errMsg = `${resp.status} ${resp.statusText || 'Error'}`;
          try {
            const clone = resp.clone();
            try {
              const errData = await clone.json();
              if (typeof errData.detail === 'string') errMsg = errData.detail;
              else if (Array.isArray(errData.detail)) errMsg = errData.detail.map(d => d.msg || JSON.stringify(d)).join(', ');
              else if (errData.message) errMsg = errData.message;
              else if (errData.error) errMsg = errData.error;
            } catch (_) {
              const rawTxt = await resp.text();
              if (rawTxt) errMsg = rawTxt;
            }
          } catch (__) {}
          alert("Transcription error: " + errMsg);
          return;
        }
        const data = await resp.json();
        document.getElementById('results-area').style.display = 'block';
        document.getElementById('res-lang').innerText = `LANG: ${(data.language_hint || 'auto').toUpperCase()} (${(data.language_probability * 100).toFixed(0)}%)`;
        document.getElementById('res-conf').innerText = `CONFIDENCE: ${(data.confidence * 100).toFixed(0)}%`;
        const durSec = (data.duration_ms / 1000).toFixed(1);
        const durMin = (data.duration_ms / 60000).toFixed(2);
        document.getElementById('res-duration').innerText = `DURATION: ${durSec}s (${durMin} min)`;
        document.getElementById('res-words-count').innerText = `WORDS: ${data.words ? data.words.length : 0}`;
        document.getElementById('res-segments-count').innerText = `SEGMENTS: ${data.segments ? data.segments.length : 0}`;
        document.getElementById('res-latency').innerText = `LATENCY: ${data.recognition_latency_ms} ms`;
        document.getElementById('words-header-count').innerText = data.words ? data.words.length : 0;
        
        // Show audio preview player
        const audioPlayer = document.getElementById('audio-preview');
        try {
          audioPlayer.src = URL.createObjectURL(selectedFile);
          audioPlayer.style.display = 'block';
        } catch (_) {}

        if (data.text && data.text.trim()) {
          document.getElementById('res-transcript').innerText = data.text;
        } else {
          document.getElementById('res-transcript').innerHTML = `<em style="color:#f59e0b;">[No spoken speech detected — audio may contain music, singing/dhun, or silence]</em>`;
        }

        const tbody = document.getElementById('words-body');
        tbody.innerHTML = '';
        if (data.words && data.words.length > 0) {
          data.words.forEach(w => {
            const row = document.createElement('tr');
            row.innerHTML = `<td><strong>${w.word}</strong></td><td>${w.start.toFixed(3)}s</td><td>${w.end.toFixed(3)}s</td><td>${(w.confidence * 100).toFixed(0)}%</td>`;
            tbody.appendChild(row);
          });
        } else {
          tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:#9ca3af;">No word segments found.</td></tr>';
        }
      } catch (e) {
        alert("Failed to transcribe: " + e.message);
      } finally {
        btn.removeAttribute('disabled');
        btn.innerText = "Transcribe Speech";
      }
    }

    async function toggleMicrophone() {
      if (isStreaming) {
        stopMicrophone();
      } else {
        await startMicrophone();
      }
    }

    async function startMicrophone() {
      try {
        mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch (e) {
        alert("Microphone permission denied: " + e.message);
        return;
      }

      const sid = 'sess_' + Math.random().toString(36).substring(2, 9);
      ws = new WebSocket(`ws://${window.location.host}/api/v1/stt/stream/${sid}`);
      ws.binaryType = 'arraybuffer';

      ws.onopen = () => {
        isStreaming = true;
        document.getElementById('btn-mic').innerText = "Stop Recognition";
        document.getElementById('btn-mic').classList.add('stop-btn');
        setupAudioRecording();
      };

      ws.onmessage = (e) => {
        try {
          const evt = JSON.parse(e.data);
          if (evt.type === 'transcript.partial') {
            document.getElementById('live-partial').innerText = evt.text;
          } else if (evt.type === 'transcript.final') {
            document.getElementById('live-partial').innerText = '...';
            const log = document.getElementById('stream-log');
            log.innerHTML += `<div style="margin-bottom:6px; color:#34d399;"><strong>[FINAL]</strong> ${evt.text} <span style="font-size:11px; color:#9ca3af;">(${evt.language}, ${evt.recognition_latency_ms}ms)</span></div>`;
            log.scrollTop = log.scrollHeight;
          }
        } catch(err) {}
      };

      ws.onclose = () => stopMicrophone();
    }

    function setupAudioRecording() {
      audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
      const source = audioContext.createMediaStreamSource(mediaStream);
      scriptProcessor = audioContext.createScriptProcessor(2048, 1, 1);
      let buffer = new Float32Array(0);

      scriptProcessor.onaudioprocess = (e) => {
        if (!isStreaming || !ws || ws.readyState !== WebSocket.OPEN) return;
        const input = e.inputBuffer.getChannelData(0);
        let merged = new Float32Array(buffer.length + input.length);
        merged.set(buffer);
        merged.set(input, buffer.length);
        buffer = merged;

        while (buffer.length >= 800) {
          let chunk = buffer.subarray(0, 800);
          buffer = buffer.subarray(800);
          let pcm16 = new Int16Array(800);
          for (let i = 0; i < 800; i++) {
            let s = Math.max(-1, Math.min(1, chunk[i]));
            pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
          }
          let frame = new Uint8Array(17 + 1600);
          frame[0] = 0x4F; // 'O'
          for (let i = 1; i < 17; i++) frame[i] = 32;
          frame.set(new Uint8Array(pcm16.buffer), 17);
          ws.send(frame.buffer);
        }
      };
      source.connect(scriptProcessor);
      scriptProcessor.connect(audioContext.destination);
    }

    function stopMicrophone() {
      isStreaming = false;
      document.getElementById('btn-mic').innerText = "Start Live Recognition";
      document.getElementById('btn-mic').classList.remove('stop-btn');
      if (scriptProcessor) { scriptProcessor.disconnect(); scriptProcessor = null; }
      if (audioContext) { audioContext.close(); audioContext = null; }
      if (mediaStream) { mediaStream.getTracks().forEach(t => t.stop()); mediaStream = null; }
      if (ws) { ws.close(); ws = null; }
    }
  </script>
</body>
</html>
"""

