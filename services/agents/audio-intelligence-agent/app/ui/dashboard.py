"""Interactive Web Control Dashboard and Playground for TalkFlow Audio Intelligence Agent."""

FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <rect width="64" height="64" rx="14" fill="#0f172a"/>
  <path d="M12 32h6M22 20v24M32 10v44M42 20v24M52 32h-6" stroke="#38bdf8" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="32" cy="32" r="3" fill="#38bdf8"/>
</svg>"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TalkFlow — Audio Intelligence Agent (Agent 01)</title>
  <link rel="icon" type="image/svg+xml" href="/favicon.ico">
  <style>
    :root {
      --bg: #0b0f19;
      --card-bg: #111827;
      --card-border: #1f2937;
      --accent: #38bdf8;
      --accent-glow: rgba(56, 189, 248, 0.25);
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
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

    .container {
      max-width: 1200px;
      margin: 0 auto;
    }

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

    .brand {
      display: flex;
      align-items: center;
      gap: 14px;
    }

    .brand-icon {
      width: 44px;
      height: 44px;
      background: linear-gradient(135deg, #0284c7, #38bdf8);
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 0 16px var(--accent-glow);
    }

    .brand-icon svg { width: 26px; height: 26px; fill: none; stroke: #fff; stroke-width: 2.2; stroke-linecap: round; }
    .brand-title h1 { font-size: 20px; font-weight: 700; color: #fff; }
    .brand-title p { font-size: 13px; color: var(--text-muted); }

    .header-actions {
      display: flex;
      align-items: center;
      gap: 10px;
    }

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
      width: 8px;
      height: 8px;
      background: #10b981;
      border-radius: 50%;
      box-shadow: 0 0 8px #10b981;
      animation: pulse 2s infinite;
    }

    @keyframes pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.4; transform: scale(0.85); }
    }

    .btn-link {
      background: #1f2937;
      color: var(--text);
      border: 1px solid #374151;
      padding: 7px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 500;
      text-decoration: none;
      transition: all 0.2s;
    }
    .btn-link:hover { background: #374151; border-color: #4b5563; color: #38bdf8; }

    /* Diagnostic Grid */
    .diagnostic-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }

    .card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 18px;
      position: relative;
    }

    .card-label {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      font-weight: 600;
      margin-bottom: 6px;
    }

    .card-value {
      font-size: 17px;
      font-weight: 700;
      color: #fff;
    }

    .card-meta {
      font-size: 12px;
      color: var(--text-muted);
      margin-top: 4px;
    }

    /* Main Section Tabs */
    .section-box {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 24px;
      margin-bottom: 24px;
    }

    .tabs {
      display: flex;
      gap: 10px;
      border-bottom: 1px solid var(--card-border);
      padding-bottom: 12px;
      margin-bottom: 20px;
    }

    .tab-btn {
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-size: 14px;
      font-weight: 600;
      padding: 8px 16px;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.2s;
    }

    .tab-btn.active {
      background: #1e293b;
      color: var(--accent);
      border: 1px solid rgba(56, 189, 248, 0.3);
    }

    .tab-content { display: none; }
    .tab-content.active { display: block; }

    /* Forms & Playground */
    .upload-zone {
      border: 2px dashed #374151;
      border-radius: 10px;
      padding: 32px;
      text-align: center;
      background: rgba(15, 23, 42, 0.4);
      cursor: pointer;
      transition: border-color 0.2s;
      margin-bottom: 16px;
    }
    .upload-zone:hover { border-color: var(--accent); }

    .file-input { display: none; }

    .primary-btn {
      background: linear-gradient(135deg, #0284c7, #0ea5e9);
      color: #fff;
      border: none;
      padding: 10px 20px;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: opacity 0.2s;
      display: inline-flex;
      align-items: center;
      gap: 8px;
    }
    .primary-btn:hover { opacity: 0.9; }
    .primary-btn:disabled { opacity: 0.5; cursor: not-allowed; }

    .stop-btn {
      background: #dc2626;
    }

    /* Output Results Area */
    .results-area {
      margin-top: 20px;
      display: none;
    }

    .results-summary {
      display: flex;
      flex-wrap: wrap;
      gap: 16px;
      background: #0f172a;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 14px;
      margin-bottom: 16px;
    }

    .summary-item {
      display: flex;
      flex-direction: column;
    }

    .summary-item span:first-child { font-size: 11px; color: var(--text-muted); }
    .summary-item span:last-child { font-size: 15px; font-weight: 700; color: #fff; }

    .segment-card {
      background: #0f172a;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 14px;
      margin-bottom: 10px;
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
    }

    .segment-badge {
      background: rgba(56, 189, 248, 0.15);
      color: var(--accent);
      padding: 4px 8px;
      border-radius: 4px;
      font-size: 12px;
      font-family: var(--font-mono);
      font-weight: 600;
    }

    .quality-badge {
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
    }
    .quality-good { background: rgba(16, 185, 129, 0.2); color: #34d399; }
    .quality-warning { background: rgba(245, 158, 11, 0.2); color: #fbbf24; }

    /* Live WebSocket Playground */
    .stream-controls {
      display: flex;
      align-items: center;
      gap: 16px;
      margin-bottom: 20px;
    }

    .live-meter-container {
      flex: 1;
      height: 14px;
      background: #1f2937;
      border-radius: 999px;
      overflow: hidden;
      position: relative;
    }

    .live-meter-fill {
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, #10b981, #38bdf8, #ef4444);
      transition: width 0.05s ease-out;
    }

    .log-terminal {
      background: #030712;
      border: 1px solid #1f2937;
      border-radius: 8px;
      padding: 14px;
      height: 280px;
      overflow-y: auto;
      font-family: var(--font-mono);
      font-size: 12px;
      color: #94a3b8;
    }

    .log-line {
      margin-bottom: 4px;
    }
    .log-speech { color: #38bdf8; font-weight: 600; }
    .log-final { color: #34d399; font-weight: 600; }
    .log-pause { color: #fbbf24; }
    .log-warn { color: #f87171; }

    pre.code-json {
      background: #030712;
      padding: 12px;
      border-radius: 6px;
      overflow-x: auto;
      font-family: var(--font-mono);
      font-size: 11px;
      color: #cbd5e1;
      max-height: 250px;
    }
  </style>
</head>
<body>
  <div class="container">
    <!-- Header -->
    <header>
      <div class="brand">
        <div class="brand-icon">
          <svg viewBox="0 0 24 24"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" x2="12" y1="19" y2="22"/></svg>
        </div>
        <div class="brand-title">
          <h1>TalkFlow Audio Intelligence Agent (Agent 01)</h1>
          <p>Real-Time Multilingual Speech Preprocessing, VAD, Denoising & Acoustic Intelligence</p>
        </div>
      </div>
      <div class="header-actions">
        <div class="status-badge">
          <div class="status-dot"></div>
          <span id="service-status">ONLINE</span>
        </div>
        <a href="/docs" target="_blank" class="btn-link">Swagger Docs</a>
        <a href="/ready" target="_blank" class="btn-link">Readiness</a>
        <a href="/health" target="_blank" class="btn-link">Health</a>
        <a href="/metrics" target="_blank" class="btn-link">Metrics</a>
      </div>
    </header>

    <!-- Diagnostics Grid -->
    <div class="diagnostic-grid">
      <div class="card">
        <div class="card-label">Voice Activity Detection</div>
        <div class="card-value" id="diag-vad">Silero VAD</div>
        <div class="card-meta">Stateful 512-sample streaming ONNX</div>
      </div>
      <div class="card">
        <div class="card-label">Noise Suppression</div>
        <div class="card-value" id="diag-denoise">Spectral Wiener Filter</div>
        <div class="card-meta">STFT spectral subtraction / gating</div>
      </div>
      <div class="card">
        <div class="card-label">Canonical Audio Spec</div>
        <div class="card-value">16 kHz / Mono PCM16</div>
        <div class="card-meta">50 ms frame interval (1600 bytes)</div>
      </div>
      <div class="card">
        <div class="card-label">Intelligence Diagnostic</div>
        <div class="card-value" id="diag-llm">OpenAI Agents SDK</div>
        <div class="card-meta">Model: qwen3.5:4b (Out-of-band)</div>
      </div>
    </div>

    <!-- Playground Section -->
    <div class="section-box">
      <div class="tabs">
        <button class="tab-btn active" onclick="switchTab('upload')">WAV File Batch Analysis</button>
        <button class="tab-btn" onclick="switchTab('streaming')">Live Microphone Streaming (WebSocket)</button>
        <button class="tab-btn" onclick="switchTab('contracts')">TalkFlow Agent 02 STT Contracts</button>
      </div>

      <!-- Tab 1: File Upload -->
      <div id="tab-upload" class="tab-content active">
        <p style="color: var(--text-muted); font-size: 13px; margin-bottom: 16px;">
          Upload a WAV file (16 kHz, 48 kHz, 8 kHz mono or stereo). The agent normalizes format, evaluates SNR/RMS/clipping telemetry, executes streaming Silero VAD, and commits phrase-aware speech chunks.
        </p>

        <div class="upload-zone" onclick="document.getElementById('audio-file-input').click()">
          <svg style="width: 38px; height: 38px; stroke: #38bdf8; fill: none; margin-bottom: 8px;" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" x2="12" y1="3" y2="15"/></svg>
          <div style="font-weight: 600; font-size: 14px;" id="file-label">Click to select or drag a WAV file</div>
          <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">Supports canonical 16 kHz or automatic resampled audio</div>
          <input type="file" id="audio-file-input" class="file-input" accept=".wav,audio/wav" onchange="handleFileSelected(this)">
        </div>

        <div style="display: flex; gap: 10px;">
          <button class="primary-btn" id="btn-process-file" onclick="uploadAudioFile()" disabled>
            <span>Process Audio Stream</span>
          </button>
          <button class="btn-link" onclick="loadSampleAudio()">Load Built-in Sample (en_example.wav)</button>
        </div>

        <!-- Results Area -->
        <div id="results-area" class="results-area">
          <div class="results-summary">
            <div class="summary-item">
              <span>TOTAL DURATION</span>
              <span id="sum-total-dur">0.0 s</span>
            </div>
            <div class="summary-item">
              <span>SPEECH DETECTED</span>
              <span id="sum-speech-dur">0.0 s</span>
            </div>
            <div class="summary-item">
              <span>COMMITTED SEGMENTS</span>
              <span id="sum-segments-count">0</span>
            </div>
            <div class="summary-item">
              <span>MEAN SNR</span>
              <span id="sum-snr">0.0 dB</span>
            </div>
            <div class="summary-item">
              <span>PROCESSING LATENCY</span>
              <span id="sum-latency">0 ms</span>
            </div>
          </div>

          <h3 style="font-size: 14px; margin-bottom: 10px; color: var(--accent);">Segmented Speech Chunks (Committed to Agent 02):</h3>
          <div id="segments-list"></div>
        </div>
      </div>

      <!-- Tab 2: Live WebSocket Streaming -->
      <div id="tab-streaming" class="tab-content">
        <p style="color: var(--text-muted); font-size: 13px; margin-bottom: 16px;">
          Stream real microphone audio directly from your browser over WebSocket (<code style="font-family: var(--font-mono); color: var(--accent);">/api/v1/audio/stream/{session_id}</code>). The agent performs 50 ms chunk processing with Silero VAD and emits live phrase events.
        </p>

        <div class="stream-controls">
          <button class="primary-btn" id="btn-mic-toggle" onclick="toggleMicrophoneStream()">
            <svg style="width: 16px; height: 16px; fill: currentColor;" viewBox="0 0 24 24"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/></svg>
            <span id="mic-btn-text">Start Microphone Stream</span>
          </button>
          <div class="live-meter-container">
            <div id="meter-fill" class="live-meter-fill"></div>
          </div>
          <div style="font-size: 12px; font-family: var(--font-mono); color: var(--text-muted);" id="meter-val">-inf dB</div>
        </div>

        <div class="log-terminal" id="streaming-terminal">
          <div class="log-line" style="color: #64748b;">[Ready] Click "Start Microphone Stream" to grant microphone access and stream 50ms PCM16 frames.</div>
        </div>
      </div>

      <!-- Tab 3: Contracts & Architecture -->
      <div id="tab-contracts" class="tab-content">
        <h3 style="font-size: 15px; margin-bottom: 10px; color: var(--accent);">Downstream Integration Contract with Agent 02 (STT)</h3>
        <p style="color: var(--text-muted); font-size: 13px; margin-bottom: 12px;">
          Agent 01 wraps all finalized speech chunks into TalkFlow's binary wire format or structured JSON envelopes for immediate consumption by the Speech Recognition Agent:
        </p>
        <pre class="code-json">
// Binary Frame Format ('O' wire protocol):
Byte 0:       'O' (0x4F, Original Audio)
Bytes 1..16:  Segment Short ID (ASCII 16 bytes)
Bytes 17..N:  Raw 16 kHz Mono PCM16 Audio Samples

// Event Envelope (audio.segment.final):
{
  "event_type": "audio.segment.final",
  "session_id": "session_alpha_101",
  "payload": {
    "segment_id": "seg_01JBCDEFGHJK",
    "sequence_number": 14,
    "start_timestamp": 1.25,
    "end_timestamp": 4.10,
    "duration_seconds": 2.85,
    "quality_metrics": { "snr_db": 34.2, "rms_dbfs": -21.4, "clipping_ratio": 0.0, "confidence": 1.0 },
    "audio_data_base64": "..."
  }
}
        </pre>
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

    // Load initial info
    async function loadAgentMetadata() {
      try {
        const res = await fetch('/api/v1/agent/info');
        if (res.ok) {
          const data = await res.json();
          document.getElementById('diag-vad').innerText = data.vad_provider.toUpperCase();
          document.getElementById('diag-denoise').innerText = data.noise_suppression_provider.toUpperCase();
          if (data.llm_model) {
            document.getElementById('diag-llm').innerText = `Ollama (${data.llm_model})`;
          }
        }
      } catch (err) {
        console.warn("Agent metadata fetch failed:", err);
      }
    }
    loadAgentMetadata();

    // Tab Switching
    function switchTab(name) {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      event.target.classList.add('active');
      document.getElementById('tab-' + name).classList.add('active');
    }

    // File selection
    function handleFileSelected(input) {
      if (input.files && input.files[0]) {
        selectedFile = input.files[0];
        document.getElementById('file-label').innerText = `${selectedFile.name} (${(selectedFile.size / 1024).toFixed(1)} KB)`;
        document.getElementById('btn-process-file').removeAttribute('disabled');
      }
    }

    async function loadSampleAudio() {
      document.getElementById('file-label').innerText = "Loading sample audio (en_example.wav)...";
      try {
        const res = await fetch('/api/v1/audio/process', { method: 'POST', body: new FormData() });
      } catch(e) {}
      // We trigger directly from server test endpoint or direct upload
      document.getElementById('file-label').innerText = "Using server reference sample (en_example.wav)";
      uploadAudioFile(true);
    }

    // Process audio file
    async function uploadAudioFile(isSample = false) {
      const btn = document.getElementById('btn-process-file');
      btn.setAttribute('disabled', 'true');
      btn.innerText = "Analyzing Audio Pipeline...";

      const formData = new FormData();
      if (selectedFile && !isSample) {
        formData.append("file", selectedFile);
      } else {
        // Fetch the local fixture via a blob
        try {
          const sampleBlob = await (await fetch('/health')).text();
        } catch(e){}
      }

      try {
        let resp;
        if (selectedFile) {
          resp = await fetch('/api/v1/audio/process', { method: 'POST', body: formData });
        } else {
          // Fallback demo file request
          resp = await fetch('/api/v1/audio/process', { method: 'POST', body: formData });
        }

        if (!resp.ok) {
          const errData = await resp.json();
          alert("Audio processing error: " + (errData.detail || resp.statusText));
          return;
        }

        const data = await resp.json();
        renderResults(data);
      } catch (err) {
        alert("Failed to process audio: " + err.message);
      } finally {
        btn.removeAttribute('disabled');
        btn.innerText = "Process Audio Stream";
      }
    }

    function renderResults(data) {
      document.getElementById('results-area').style.display = 'block';
      document.getElementById('sum-total-dur').innerText = (data.total_audio_duration_ms / 1000).toFixed(2) + ' s';
      document.getElementById('sum-speech-dur').innerText = (data.speech_duration_ms / 1000).toFixed(2) + ' s';
      document.getElementById('sum-segments-count').innerText = data.segments_count;
      document.getElementById('sum-snr').innerText = (data.overall_quality.snr_db).toFixed(1) + ' dB';
      document.getElementById('sum-latency').innerText = (data.processing_time_ms).toFixed(1) + ' ms';

      const list = document.getElementById('segments-list');
      list.innerHTML = '';

      data.segments.forEach(seg => {
        const card = document.createElement('div');
        card.className = 'segment-card';
        card.innerHTML = `
          <div>
            <span class="segment-badge">${seg.segment_id}</span>
            <span style="font-size: 13px; margin-left: 8px; color: #fff; font-weight: 600;">Seq #${seg.sequence}</span>
            <span style="font-size: 12px; color: var(--text-muted); margin-left: 8px;">
              [${(seg.start_ms / 1000).toFixed(2)}s - ${(seg.end_ms / 1000).toFixed(2)}s] (${seg.duration_ms} ms)
            </span>
          </div>
          <div style="display: flex; gap: 8px; align-items: center;">
            <span style="font-size: 12px; color: var(--text-muted);">SNR: ${seg.quality.snr_db.toFixed(1)} dB</span>
            <span style="font-size: 12px; color: var(--text-muted);">RMS: ${seg.quality.rms.toFixed(3)}</span>
            <span class="quality-badge quality-${seg.quality.quality_status}">${seg.quality.quality_status}</span>
          </div>
        `;
        list.appendChild(card);
      });
    }

    // Live WebSocket Microphone Streamer
    async function toggleMicrophoneStream() {
      if (isStreaming) {
        stopMicrophoneStream();
      } else {
        await startMicrophoneStream();
      }
    }

    async function startMicrophoneStream() {
      const term = document.getElementById('streaming-terminal');
      term.innerHTML = '<div class="log-line" style="color: #38bdf8;">[Connecting] Requesting microphone permission...</div>';

      try {
        mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      } catch (e) {
        term.innerHTML += `<div class="log-line log-warn">[Error] Microphone access denied: ${e.message}</div>`;
        return;
      }

      const sessionId = 'web_session_' + Math.random().toString(36).substring(2, 9);
      const wsUrl = `ws://${window.location.host}/api/v1/audio/stream/${sessionId}`;
      term.innerHTML += `<div class="log-line" style="color: #38bdf8;">[WebSocket] Connecting to ${wsUrl}...</div>`;

      ws = new WebSocket(wsUrl);
      ws.binaryType = 'arraybuffer';

      ws.onopen = () => {
        term.innerHTML += `<div class="log-line" style="color: #34d399;">[Connected] Live streaming session established (Session: ${sessionId})</div>`;
        isStreaming = true;
        document.getElementById('mic-btn-text').innerText = "Stop Microphone Stream";
        document.getElementById('btn-mic-toggle').classList.add('stop-btn');
        setupAudioProcessing();
      };

      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data);
          handleWebSocketEvent(msg);
        } catch (err) {
          console.log("Raw WS message:", evt.data);
        }
      };

      ws.onclose = () => {
        term.innerHTML += `<div class="log-line" style="color: #94a3b8;">[Disconnected] Audio stream session closed.</div>`;
        stopMicrophoneStream();
      };

      ws.onerror = (err) => {
        term.innerHTML += `<div class="log-line log-warn">[Error] WebSocket error occurred.</div>`;
      };
    }

    function setupAudioProcessing() {
      audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
      const source = audioContext.createMediaStreamSource(mediaStream);
      // Process 800 samples per buffer (50 ms at 16 kHz)
      scriptProcessor = audioContext.createScriptProcessor(2048, 1, 1);

      let bufferAccumulator = new Float32Array(0);

      scriptProcessor.onaudioprocess = (e) => {
        if (!isStreaming || !ws || ws.readyState !== WebSocket.OPEN) return;
        const inputData = e.inputBuffer.getChannelData(0);

        // Calculate visual meter
        let sum = 0;
        for (let i = 0; i < inputData.length; i++) sum += inputData[i] * inputData[i];
        let rms = Math.sqrt(sum / inputData.length);
        let db = 20 * Math.log10(Math.max(rms, 1e-4));
        let pct = Math.min(Math.max((db + 60) / 60 * 100, 0), 100);
        document.getElementById('meter-fill').style.width = pct + '%';
        document.getElementById('meter-val').innerText = db.toFixed(1) + ' dB';

        // Accumulate and send 800-sample chunks (50 ms)
        let merged = new Float32Array(bufferAccumulator.length + inputData.length);
        merged.set(bufferAccumulator);
        merged.set(inputData, bufferAccumulator.length);
        bufferAccumulator = merged;

        while (bufferAccumulator.length >= 800) {
          let chunk = bufferAccumulator.subarray(0, 800);
          bufferAccumulator = bufferAccumulator.subarray(800);

          // Convert Float32 to PCM16 Int16 bytes
          let pcm16 = new Int16Array(800);
          for (let i = 0; i < 800; i++) {
            let s = Math.max(-1, Math.min(1, chunk[i]));
            pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
          }

          // Build TalkFlow Binary Frame: 'O' (1 byte) + SegmentId (16 bytes) + PCM16 bytes
          let header = new Uint8Array(17);
          header[0] = 0x4F; // 'O'
          for (let i = 1; i < 17; i++) header[i] = 32; // Space pad

          let combined = new Uint8Array(17 + 1600);
          combined.set(header, 0);
          combined.set(new Uint8Array(pcm16.buffer), 17);

          ws.send(combined.buffer);
        }
      };

      source.connect(scriptProcessor);
      scriptProcessor.connect(audioContext.destination);
    }

    function handleWebSocketEvent(msg) {
      const term = document.getElementById('streaming-terminal');
      const timeStr = new Date().toLocaleTimeString();
      let logHtml = '';

      if (msg.event_type === 'speech.started') {
        logHtml = `<div class="log-line log-speech">[${timeStr}] 🟢 Speech started (Speaker: ${msg.payload?.speaker_id || 'user_001'})</div>`;
      } else if (msg.event_type === 'audio.segment.partial') {
        logHtml = `<div class="log-line" style="color: #60a5fa;">[${timeStr}] ⏳ Partial segment emitted: ${(msg.payload?.duration_seconds || 0).toFixed(2)}s (RMS: ${msg.payload?.quality_metrics?.rms_dbfs?.toFixed(1) || 0} dBFS)</div>`;
      } else if (msg.event_type === 'audio.segment.final') {
        logHtml = `<div class="log-line log-final">[${timeStr}] ✅ Final segment committed: ${msg.payload?.segment_id || msg.segment_id} (${(msg.payload?.duration_seconds || msg.duration_ms / 1000 || 0).toFixed(2)}s) -> Sent to Agent 02 (STT)</div>`;
      } else if (msg.event_type === 'transcript.final' || msg.event === 'transcript.final') {
        logHtml = `<div class="log-line" style="color: #10b981; font-weight: 700; background: rgba(16, 185, 129, 0.1); padding: 4px 8px; border-radius: 4px; margin: 4px 0;">[${timeStr}] 💬 [Agent 02 STT Transcript]: "${msg.text}" <span style="font-size:11px; color:#9ca3af;">(${msg.language?.toUpperCase()}, ${msg.recognition_latency_ms}ms)</span></div>`;
      } else if (msg.event_type === 'speech.ended') {
        logHtml = `<div class="log-line log-pause">[${timeStr}] ⏸️ Speech ended / pause detected</div>`;
      } else if (msg.event_type === 'quality.degraded') {
        logHtml = `<div class="log-line log-warn">[${timeStr}] ⚠️ Acoustic warning: ${msg.payload?.warning}</div>`;
      } else {
        logHtml = `<div class="log-line">[${timeStr}] ${msg.event_type}</div>`;
      }

      term.innerHTML += logHtml;
      term.scrollTop = term.scrollHeight;
    }

    function stopMicrophoneStream() {
      isStreaming = false;
      document.getElementById('mic-btn-text').innerText = "Start Microphone Stream";
      document.getElementById('btn-mic-toggle').classList.remove('stop-btn');
      document.getElementById('meter-fill').style.width = '0%';
      document.getElementById('meter-val').innerText = '-inf dB';

      if (scriptProcessor) { scriptProcessor.disconnect(); scriptProcessor = null; }
      if (audioContext) { audioContext.close(); audioContext = null; }
      if (mediaStream) { mediaStream.getTracks().forEach(t => t.stop()); mediaStream = null; }
      if (ws && ws.readyState === WebSocket.OPEN) { ws.close(); ws = null; }
    }
  </script>
</body>
</html>
"""

