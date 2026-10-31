"""Interactive Web Dashboard and Live Playground for TalkFlow Language Intelligence Agent (Agent 03)."""
from __future__ import annotations

FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="6" fill="#0f172a"/>
  <path d="M16 4C9.37 4 4 9.37 4 16c0 6.63 5.37 12 12 12s12-5.37 12-12c0-6.63-5.37-12-12-12zm-2 17.5v-11l8 5.5-8 5.5z" fill="#06b6d4"/>
</svg>"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TalkFlow Language Intelligence Agent (Agent 03)</title>
  <link rel="icon" type="image/svg+xml" href="/favicon.ico">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #090d16;
      --card-bg: #111827;
      --card-border: #1f2937;
      --accent: #06b6d4;
      --accent-hover: #0891b2;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      --font-mono: 'JetBrains Mono', monospace;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      color: var(--text);
      font-family: var(--font-sans);
      line-height: 1.5;
      padding: 24px;
    }
    .container { max-width: 1200px; margin: 0 auto; }
    header {
      display: flex; justify-content: space-between; align-items: center;
      padding-bottom: 20px; border-bottom: 1px solid var(--card-border); margin-bottom: 24px;
    }
    .brand { display: flex; align-items: center; gap: 14px; }
    .brand-icon {
      width: 44px; height: 44px; background: rgba(6, 182, 212, 0.15); border: 1px solid var(--accent);
      border-radius: 10px; display: flex; align-items: center; justify-content: center;
    }
    .brand-icon svg { width: 24px; height: 24px; stroke: var(--accent); fill: none; stroke-width: 2; }
    .brand-title h1 { font-size: 20px; font-weight: 700; color: #fff; }
    .brand-title p { font-size: 13px; color: var(--text-muted); }
    .header-actions { display: flex; align-items: center; gap: 12px; }
    .status-badge {
      display: inline-flex; align-items: center; gap: 6px; padding: 4px 12px;
      border-radius: 20px; font-size: 12px; font-weight: 600; background: rgba(16, 185, 129, 0.15);
      color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3);
    }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; background: #10b981; animation: pulse 2s infinite; }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }
    .btn-link {
      color: var(--text-muted); text-decoration: none; font-size: 13px; font-weight: 500;
      padding: 6px 12px; border-radius: 6px; border: 1px solid var(--card-border); transition: all 0.2s;
    }
    .btn-link:hover { color: #fff; background: var(--card-border); }
    .diagnostic-grid {
      display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 16px; margin-bottom: 24px;
    }
    .card {
      background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px;
      padding: 16px; display: flex; flex-direction: column; gap: 6px;
    }
    .card-label { font-size: 12px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
    .card-value { font-size: 18px; font-weight: 700; color: #fff; font-family: var(--font-mono); }
    .card-meta { font-size: 11px; color: var(--text-muted); }
    .section-box {
      background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px;
      padding: 24px; margin-bottom: 24px;
    }
    .tabs { display: flex; gap: 8px; border-bottom: 1px solid var(--card-border); padding-bottom: 12px; margin-bottom: 20px; }
    .tab-btn {
      background: transparent; border: none; color: var(--text-muted); font-size: 14px;
      font-weight: 600; padding: 8px 16px; border-radius: 6px; cursor: pointer; transition: all 0.2s;
    }
    .tab-btn:hover { color: #fff; background: rgba(255,255,255,0.05); }
    .tab-btn.active { color: var(--accent); background: rgba(6, 182, 212, 0.1); }
    .tab-content { display: none; }
    .tab-content.active { display: block; }
    .quick-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }
    .chip {
      background: #1f2937; border: 1px solid #374151; color: #d1d5db; font-size: 12px;
      padding: 5px 12px; border-radius: 16px; cursor: pointer; transition: all 0.2s;
    }
    .chip:hover { border-color: var(--accent); color: #fff; background: rgba(6, 182, 212, 0.15); }
    textarea.text-input {
      width: 100%; height: 90px; background: #0f172a; border: 1px solid var(--card-border);
      border-radius: 8px; padding: 12px; color: #fff; font-size: 14px; font-family: var(--font-sans);
      resize: vertical; margin-bottom: 14px; outline: none;
    }
    textarea.text-input:focus { border-color: var(--accent); }
    .primary-btn {
      background: var(--accent); color: #090d16; font-size: 14px; font-weight: 600;
      padding: 10px 20px; border-radius: 8px; border: none; cursor: pointer;
      display: inline-flex; align-items: center; gap: 8px; transition: all 0.2s;
    }
    .primary-btn:hover { background: var(--accent-hover); }
    .results-area {
      display: none; margin-top: 24px; padding-top: 20px; border-top: 1px solid var(--card-border);
    }
    .badge {
      display: inline-block; padding: 4px 10px; border-radius: 6px; font-size: 12px;
      font-weight: 700; margin-right: 8px; font-family: var(--font-mono);
    }
    .badge-primary { background: rgba(6, 182, 212, 0.2); color: var(--accent); border: 1px solid var(--accent); }
    .badge-conf { background: rgba(16, 185, 129, 0.2); color: #34d399; }
    .badge-lat { background: rgba(245, 158, 11, 0.2); color: #fbbf24; }
    .badge-multi { background: rgba(168, 85, 247, 0.2); color: #c084fc; border: 1px solid #a855f7; }
    .span-box {
      background: #0f172a; border: 1px solid var(--card-border); border-radius: 8px;
      padding: 16px; margin: 16px 0; font-size: 15px; line-height: 1.8;
    }
    .hl-span {
      padding: 3px 6px; border-radius: 4px; font-weight: 600; display: inline-block; margin: 2px 0;
    }
    .hl-en { background: rgba(56, 189, 248, 0.25); color: #38bdf8; border: 1px solid #0284c7; }
    .hl-hi { background: rgba(16, 185, 129, 0.25); color: #34d399; border: 1px solid #059669; }
    .hl-mr { background: rgba(245, 158, 11, 0.25); color: #fbbf24; border: 1px solid #d97706; }
    .hl-other { background: rgba(168, 85, 247, 0.25); color: #c084fc; border: 1px solid #7c3aed; }
    .hl-tag { font-size: 10px; font-family: var(--font-mono); opacity: 0.85; margin-left: 4px; }
    table.data-table {
      width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 12px;
    }
    table.data-table th, table.data-table td {
      padding: 10px 12px; border: 1px solid var(--card-border); text-align: left;
    }
    table.data-table th { background: #1f2937; color: var(--text-muted); font-weight: 600; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="brand">
        <div class="brand-icon">
          <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
        </div>
        <div class="brand-title">
          <h1>TalkFlow Language Intelligence Agent (Agent 03)</h1>
          <p>Multi-Signal Language Identification, Code-Switching & Indian Language Disambiguation</p>
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
        <div class="card-label">Primary Text LID</div>
        <div class="card-value" id="diag-primary">fastText</div>
        <div class="card-meta">176 Languages / Direct C++ Inference</div>
      </div>
      <div class="card">
        <div class="card-label">Indic Disambiguation</div>
        <div class="card-value">langdetect + Regex</div>
        <div class="card-meta">Hindi vs. Marathi Devanagari Markers</div>
      </div>
      <div class="card">
        <div class="card-label">Evidence Fusion</div>
        <div class="card-value">Multi-Modal</div>
        <div class="card-meta">Text + STT Hint + Script + Speaker Context</div>
      </div>
      <div class="card">
        <div class="card-label">Operational Reasoning</div>
        <div class="card-value" id="diag-brain">OpenAI Agents SDK</div>
        <div class="card-meta">Ollama (qwen3.5:4b) Diagnostic Telemetry</div>
      </div>
    </div>

    <div class="section-box">
      <div class="tabs">
        <button class="tab-btn active" onclick="switchTab('playground')">Live Language & Code-Switching Playground</button>
        <button class="tab-btn" onclick="switchTab('capabilities')">TalkFlow Capability Matrix</button>
      </div>

      <!-- Tab 1: Playground -->
      <div id="tab-playground" class="tab-content active">
        <div class="quick-chips">
          <span style="font-size:12px; color:var(--text-muted); align-self:center;">Try Presets:</span>
          <div class="chip" onclick="setPreset('Hello everyone, aaj hum artificial intelligence ke baare mein discuss karenge.')">Hinglish Code-Switch</div>
          <div class="chip" onclick="setPreset('Hello everyone, today we will talk about the real-time translation architecture.')">English</div>
          <div class="chip" onclick="setPreset('नमस्ते दोस्तों, आज हम एआई मॉडल और वास्तविक समय अनुवाद के बारे में चर्चा करेंगे।')">Hindi (Devanagari)</div>
          <div class="chip" onclick="setPreset('नमस्कार मित्रांनो, आज आपण काय करणार आहोत? तुम्ही कसे आहात?')">Marathi (Devanagari)</div>
          <div class="chip" onclick="setPreset('Hi')">Short Ambiguous (Fail-Closed)</div>
        </div>

        <textarea id="sample-text" class="text-input" placeholder="Type or paste multilingual speech transcript..."></textarea>

        <button class="primary-btn" onclick="analyzeText()">
          <svg style="width:16px; height:16px;" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          Analyze Language Intelligence
        </button>

        <div id="results-area" class="results-area">
          <div style="margin-bottom: 12px;">
            <span class="badge badge-primary" id="res-primary">LANG: EN</span>
            <span class="badge badge-conf" id="res-conf">CONFIDENCE: 98%</span>
            <span class="badge badge-lat" id="res-lat">LATENCY: 1.2 ms</span>
            <span class="badge badge-multi" id="res-multi" style="display:none;">CODE-SWITCHING DETECTED</span>
          </div>

          <h3 style="font-size: 13px; color: var(--accent); margin-bottom: 6px;">Visual Code-Switching Span Segmentation:</h3>
          <div class="span-box" id="res-spans-visual"></div>

          <h3 style="font-size: 13px; color: var(--text-muted); margin: 16px 0 6px 0;">Exact Character Offsets & Timings:</h3>
          <table class="data-table" id="spans-table">
            <thead>
              <tr>
                <th>Span Text</th><th>Language</th><th>Script</th><th>Char Offsets</th><th>Confidence</th>
              </tr>
            </thead>
            <tbody id="spans-body"></tbody>
          </table>
        </div>
      </div>

      <!-- Tab 2: Capabilities Matrix -->
      <div id="tab-capabilities" class="tab-content">
        <p style="color: var(--text-muted); font-size: 13px; margin-bottom: 16px;">
          TalkFlow operational translation capabilities matrix across production, experimental, and unsupported tiers.
        </p>
        <table class="data-table">
          <thead>
            <tr><th>Language</th><th>Code</th><th>Tier</th><th>STT Supported</th><th>MT Supported</th><th>Routing Recommendation</th></tr>
          </thead>
          <tbody id="capabilities-body"></tbody>
        </table>
      </div>
    </div>
  </div>

  <script>
    function setPreset(t) {
      document.getElementById('sample-text').value = t;
      analyzeText();
    }

    function switchTab(t) {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      event.target.classList.add('active');
      document.getElementById('tab-' + t).classList.add('active');
      if (t === 'capabilities') loadCapabilities();
    }

    async function analyzeText() {
      const text = document.getElementById('sample-text').value.trim();
      if (!text) return;

      try {
        const resp = await fetch('/api/v1/language/analyze', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ text: text, session_id: 'sess_playground' })
        });
        if (!resp.ok) {
          alert('Analysis error: ' + resp.statusText);
          return;
        }
        const data = await resp.json();
        renderResults(data);
      } catch (err) {
        alert('Failed to analyze: ' + err.message);
      }
    }

    function renderResults(data) {
      document.getElementById('results-area').style.display = 'block';
      document.getElementById('res-primary').innerText = `PRIMARY: ${data.primary_language.toUpperCase()} (${data.primary_language_script})`;
      document.getElementById('res-conf').innerText = `CONFIDENCE: ${(data.confidence * 100).toFixed(1)}%`;
      document.getElementById('res-lat').innerText = `LATENCY: ${data.analysis_latency_ms} ms`;

      const multiBadge = document.getElementById('res-multi');
      if (data.is_multilingual) {
        multiBadge.style.display = 'inline-block';
        multiBadge.innerText = `MULTILINGUAL (+${data.secondary_languages.join(', ').toUpperCase()})`;
      } else {
        multiBadge.style.display = 'none';
      }

      // Visual spans
      const visual = document.getElementById('res-spans-visual');
      visual.innerHTML = '';
      if (!data.language_spans || data.language_spans.length === 0) {
        visual.innerText = data.original_text;
      } else {
        data.language_spans.forEach(s => {
          let cls = 'hl-other';
          if (s.language === 'en') cls = 'hl-en';
          else if (s.language === 'hi') cls = 'hl-hi';
          else if (s.language === 'mr') cls = 'hl-mr';
          visual.innerHTML += `<span class="hl-span ${cls}">${s.text} <span class="hl-tag">[${s.language.toUpperCase()}]</span></span> `;
        });
      }

      // Table spans
      const tbody = document.getElementById('spans-body');
      tbody.innerHTML = '';
      data.language_spans.forEach(s => {
        const row = document.createElement('tr');
        row.innerHTML = `
          <td><strong>${s.text}</strong></td>
          <td>${s.language.toUpperCase()}</td>
          <td>${s.script}</td>
          <td>[${s.text_start_offset} : ${s.text_end_offset}]</td>
          <td>${(s.confidence * 100).toFixed(0)}%</td>
        `;
        tbody.appendChild(row);
      });
    }

    async function loadCapabilities() {
      try {
        const r = await fetch('/api/v1/language/capabilities');
        if (r.ok) {
          const items = await r.json();
          const body = document.getElementById('capabilities-body');
          body.innerHTML = '';
          items.forEach(i => {
            const row = document.createElement('tr');
            row.innerHTML = `
              <td><strong>${i.name}</strong></td>
              <td>${i.language.toUpperCase()}</td>
              <td><span style="color:${i.capability === 'production' ? '#10b981' : (i.capability === 'experimental' ? '#f59e0b' : '#ef4444')}">${i.capability.toUpperCase()}</span></td>
              <td>${i.stt_supported ? 'Yes' : 'No'}</td>
              <td>${i.mt_supported ? 'Yes' : 'No'}</td>
              <td style="font-family:var(--font-mono); font-size:11px;">${i.routing_recommendation}</td>
            `;
            body.appendChild(row);
          });
        }
      } catch (_) {}
    }
  </script>
</body>
</html>
"""

