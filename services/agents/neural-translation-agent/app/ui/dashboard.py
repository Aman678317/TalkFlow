"""Interactive web dashboard for Neural Translation Agent (Agent 04)."""
from __future__ import annotations

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TalkFlow Neural Translation Agent (Agent 04)</title>
  <style>
    :root {
      --bg: #090d16;
      --card-bg: #111827;
      --border: #1f2937;
      --accent: #8b5cf6;
      --accent-glow: rgba(139, 92, 246, 0.25);
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --green: #10b981;
      --yellow: #f59e0b;
      --red: #ef4444;
      --font-mono: 'SF Mono', Consolas, Monaco, monospace;
      --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg); color: var(--text); font-family: var(--font-sans);
      min-height: 100vh; padding: 24px;
    }
    .container { max-width: 1200px; margin: 0 auto; }
    header {
      display: flex; justify-content: space-between; align-items: center;
      padding-bottom: 20px; border-bottom: 1px solid var(--border); margin-bottom: 24px;
    }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand-icon {
      width: 44px; height: 44px; border-radius: 10px; background: var(--accent-glow);
      display: flex; align-items: center; justify-content: center; border: 1px solid var(--accent);
    }
    .brand-icon svg { width: 24px; height: 24px; stroke: var(--accent); fill: none; stroke-width: 2; }
    .brand-title h1 { font-size: 20px; font-weight: 700; color: #fff; }
    .brand-title p { font-size: 13px; color: var(--text-muted); }
    .status-badge {
      display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px;
      border-radius: 20px; background: rgba(16, 185, 129, 0.15); border: 1px solid var(--green);
      font-size: 12px; font-weight: 600; color: var(--green);
    }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--green); animation: pulse 2s infinite; }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }

    .diagnostic-grid {
      display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px; margin-bottom: 24px;
    }
    .card {
      background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px;
      padding: 18px; position: relative; overflow: hidden;
    }
    .card-label { font-size: 11px; text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.5px; font-weight: 600; }
    .card-value { font-size: 18px; font-weight: 700; color: #fff; margin-top: 6px; font-family: var(--font-mono); }
    .card-meta { font-size: 12px; color: var(--accent); margin-top: 4px; }

    .tabs { display: flex; gap: 8px; border-bottom: 1px solid var(--border); margin-bottom: 20px; }
    .tab-btn {
      padding: 10px 18px; background: transparent; border: none; border-bottom: 2px solid transparent;
      color: var(--text-muted); font-size: 14px; font-weight: 600; cursor: pointer; transition: all 0.2s;
    }
    .tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); }
    .tab-content { display: none; }
    .tab-content.active { display: block; }

    .input-group { margin-bottom: 16px; }
    .input-label { display: block; font-size: 13px; font-weight: 600; margin-bottom: 6px; color: var(--text-muted); }
    textarea, input[type="text"], select {
      width: 100%; background: #0c121e; border: 1px solid var(--border); border-radius: 8px;
      padding: 12px; color: #fff; font-size: 14px; font-family: var(--font-sans); outline: none;
    }
    textarea:focus, input[type="text"]:focus, select:focus { border-color: var(--accent); }
    .btn {
      padding: 12px 24px; border-radius: 8px; font-weight: 600; font-size: 14px;
      cursor: pointer; border: none; transition: 0.2s; display: inline-flex; align-items: center; gap: 8px;
    }
    .btn-primary { background: var(--accent); color: #fff; }
    .btn-primary:hover { opacity: 0.9; }

    .output-box {
      background: #0c121e; border: 1px solid var(--border); border-radius: 8px;
      padding: 16px; min-height: 80px; font-size: 15px; margin-top: 14px; line-height: 1.6;
    }
    .results-grid {
      display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 16px; margin-top: 16px;
    }
    .target-card {
      background: #0c121e; border: 1px solid var(--border); border-radius: 8px; padding: 14px;
    }
    .target-header { display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 12px; color: var(--accent); font-weight: 700; }
    .target-text { font-size: 14px; color: #fff; line-height: 1.5; }
    .badge {
      display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px;
      font-weight: 600; background: rgba(139, 92, 246, 0.2); color: var(--accent);
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="brand">
        <div class="brand-icon">
          <svg viewBox="0 0 24 24"><path d="m5 8 6 6"/><path d="m4 14 6-6 2-3"/><path d="M2 5h12"/><path d="M7 2h1"/><path d="m22 22-5-10-5 10"/><path d="M14 18h6"/></svg>
        </div>
        <div class="brand-title">
          <h1>TalkFlow Neural Translation Agent (Agent 04)</h1>
          <p>Zero-Pivot Multi-Target Translation, Hinglish Code-Switching & Terminology Preservation</p>
        </div>
      </div>
      <div style="display: flex; gap: 10px; align-items: center;">
        <div class="status-badge"><div class="status-dot"></div><span>ONLINE (PORT 8004)</span></div>
        <a href="/docs" target="_blank" style="color: var(--accent); text-decoration: none; font-size: 13px; font-weight: 600;">API Docs</a>
      </div>
    </header>

    <div class="diagnostic-grid">
      <div class="card">
        <div class="card-label">Primary Provider</div>
        <div class="card-value" id="diag-provider">argos</div>
        <div class="card-meta">Self-Hosted / Offline Ready</div>
      </div>
      <div class="card">
        <div class="card-label">Zero-Pivot Invariant</div>
        <div class="card-value" style="color: var(--green);">ENFORCED</div>
        <div class="card-meta">Canonical Source $\to$ Direct Targets</div>
      </div>
      <div class="card">
        <div class="card-label">Active Providers</div>
        <div class="card-value" id="diag-providers-count">6</div>
        <div class="card-meta">MADLAD, NLLB, Argos, Marian, Online, Qwen</div>
      </div>
      <div class="card">
        <div class="card-label">Operational Reasoning</div>
        <div class="card-value" id="diag-brain">OpenAI Agents SDK</div>
        <div class="card-meta">Ollama (qwen3.5:4b)</div>
      </div>
    </div>

    <div class="tabs">
      <button class="tab-btn active" onclick="switchTab('single')">Single-Target Translation</button>
      <button class="tab-btn" onclick="switchTab('fanout')">Multi-Target Independent Fan-Out</button>
      <button class="tab-btn" onclick="switchTab('codeswitch')">Hinglish Code-Switching</button>
      <button class="tab-btn" onclick="switchTab('pairs')">Language Pair Capabilities</button>
    </div>

    <!-- Tab 1: Single Target -->
    <div id="tab-single" class="tab-content active">
      <div class="input-group">
        <label class="input-label">Source Text (Canonical Human Transcript from Agent 02/03):</label>
        <textarea id="single-text" rows="3">आज हम अपने नए AI प्रोजेक्ट के बारे में चर्चा करेंगे।</textarea>
      </div>
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px;">
        <div>
          <label class="input-label">Source Language:</label>
          <select id="single-src">
            <option value="hi" selected>Hindi (hi)</option>
            <option value="en">English (en)</option>
            <option value="mr">Marathi (mr)</option>
            <option value="auto">Auto Detect</option>
          </select>
        </div>
        <div>
          <label class="input-label">Target Language:</label>
          <select id="single-tgt">
            <option value="en" selected>English (en)</option>
            <option value="mr">Marathi (mr)</option>
            <option value="hi">Hindi (hi)</option>
            <option value="ja">Japanese (ja)</option>
            <option value="bn">Bengali (bn)</option>
          </select>
        </div>
      </div>
      <button class="btn btn-primary" onclick="translateSingle()">Translate Speech Transcript</button>
      <div class="output-box" id="single-output">[Translation result will appear here]</div>
      <div style="margin-top: 8px; display: flex; gap: 10px;" id="single-meta"></div>
    </div>

    <!-- Tab 2: Multi-Target Fan-Out -->
    <div id="tab-fanout" class="tab-content">
      <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 12px;">
        Demonstration of TalkFlow's core invariant: One canonical source segment is translated <strong>independently</strong> into multiple listener languages simultaneously. Zero chained pivots!
      </p>
      <div class="input-group">
        <label class="input-label">Speaker Utterance (Hindi):</label>
        <textarea id="fanout-text" rows="3">नमस्ते दोस्तों, आज हम कृत्रिम बुद्धिमत्ता के बारे में बात करेंगे।</textarea>
      </div>
      <button class="btn btn-primary" onclick="translateFanout()">Fan-Out to All Listeners (EN, MR, JA, BN)</button>
      <div class="results-grid" id="fanout-grid"></div>
    </div>

    <!-- Tab 3: Hinglish -->
    <div id="tab-codeswitch" class="tab-content">
      <div class="input-group">
        <label class="input-label">Hinglish Code-Switched Transcript:</label>
        <textarea id="cs-text" rows="3">Hello everyone, aaj hum new AI project ka architecture discuss karenge.</textarea>
      </div>
      <button class="btn btn-primary" onclick="translateCodeSwitch()">Translate Hinglish (Preserve Technical Terms)</button>
      <div class="output-box" id="cs-output">[Result will appear here]</div>
    </div>

    <!-- Tab 4: Capabilities -->
    <div id="tab-pairs" class="tab-content">
      <div class="results-grid" id="pairs-grid"></div>
    </div>
  </div>

  <script>
    function switchTab(t) {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      event.target.classList.add('active');
      document.getElementById('tab-' + t).classList.add('active');
    }

    async function loadInfo() {
      try {
        const res = await fetch('/api/v1/agent/info');
        if (res.ok) {
          const d = await res.json();
          document.getElementById('diag-provider').innerText = d.primary_provider;
          document.getElementById('diag-providers-count').innerText = d.active_providers.length;
        }
        const pairsRes = await fetch('/api/v1/translation/language-pairs');
        if (pairsRes.ok) {
          const pairs = await pairsRes.json();
          const grid = document.getElementById('pairs-grid');
          grid.innerHTML = '';
          pairs.forEach(p => {
            const card = document.createElement('div');
            card.className = 'target-card';
            card.innerHTML = `
              <div class="target-header">
                <span>${p.source_lang.toUpperCase()} &rarr; ${p.target_lang.toUpperCase()}</span>
                <span class="badge">${p.status}</span>
              </div>
              <div style="font-size: 13px; color: var(--text-muted);">Provider: ${p.preferred_provider}</div>
              <div style="font-size: 12px; color: var(--accent); margin-top: 4px;">BLEU: ${p.bleu_score || 'N/A'} | Direct: ${p.direct ? 'Yes' : 'No'}</div>
            `;
            grid.appendChild(card);
          });
        }
      } catch (e) {}
    }
    loadInfo();

    async function translateSingle() {
      const text = document.getElementById('single-text').value;
      const src = document.getElementById('single-src').value;
      const tgt = document.getElementById('single-tgt').value;
      const out = document.getElementById('single-output');
      out.innerText = "Translating...";

      const res = await fetch('/api/v1/translation/translate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({text: text, source_lang: src, target_lang: tgt})
      });
      const data = await res.json();
      out.innerText = data.text;
      document.getElementById('single-meta').innerHTML = `
        <span class="badge">PROVIDER: ${data.provider}</span>
        <span class="badge">MODEL: ${data.model}</span>
        <span class="badge">LATENCY: ${data.latency_ms}ms</span>
        ${data.pivoted ? '<span class="badge" style="color:var(--yellow)">PIVOTED</span>' : ''}
      `;
    }

    async function translateFanout() {
      const text = document.getElementById('fanout-text').value;
      const grid = document.getElementById('fanout-grid');
      grid.innerHTML = 'Fanning out independent target translations...';

      const res = await fetch('/api/v1/translation/batch', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          text: text,
          source_lang: "hi",
          target_langs: ["en", "mr", "ja", "bn"]
        })
      });
      const data = await res.json();
      grid.innerHTML = '';
      for (const [tgt, r] of Object.entries(data.results)) {
        const card = document.createElement('div');
        card.className = 'target-card';
        card.innerHTML = `
          <div class="target-header">
            <span>TARGET: ${tgt.toUpperCase()}</span>
            <span>${r.latency_ms}ms</span>
          </div>
          <div class="target-text">${r.text}</div>
          <div style="font-size: 11px; color: var(--text-muted); margin-top: 6px;">Provider: ${r.provider} (${r.model})</div>
        `;
        grid.appendChild(card);
      }
    }

    async function translateCodeSwitch() {
      const text = document.getElementById('cs-text').value;
      const out = document.getElementById('cs-output');
      out.innerText = "Processing Hinglish code-switching...";

      const res = await fetch('/api/v1/translation/translate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({text: text, source_lang: "hi", target_lang: "en"})
      });
      const data = await res.json();
      out.innerText = data.text;
    }
  </script>
</body>
</html>
"""

