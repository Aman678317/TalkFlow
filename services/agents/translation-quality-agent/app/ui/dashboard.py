"""Interactive dark-mode dashboard for Translation Quality Agent (Port 8005)."""
from __future__ import annotations

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TalkFlow Translation Quality Agent (Agent 05)</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #0b0f19;
      --card-bg: #111827;
      --card-inner: #0b1120;
      --border: #1f2937;
      --accent: #ec4899;   /* pink/rose */
      --accept: #10b981;   /* emerald */
      --warn: #f59e0b;     /* amber */
      --reject: #ef4444;   /* red */
      --retry: #8b5cf6;    /* purple */
      --text: #f9fafb;
      --text-muted: #9ca3af;
      --font-sans: 'Inter', sans-serif;
      --font-mono: 'JetBrains Mono', monospace;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: var(--bg); color: var(--text); font-family: var(--font-sans); padding: 24px; }
    .container { max-width: 1280px; margin: 0 auto; }
    
    header {
      display: flex; justify-content: space-between; align-items: center;
      border-bottom: 1px solid var(--border); padding-bottom: 18px; margin-bottom: 24px;
    }
    .brand { display: flex; align-items: center; gap: 14px; }
    .brand-icon {
      width: 44px; height: 44px; border-radius: 12px;
      background: linear-gradient(135deg, #ec4899, #8b5cf6);
      display: flex; align-items: center; justify-content: center;
      font-weight: 800; font-size: 20px; color: #fff; box-shadow: 0 4px 14px rgba(236, 72, 153, 0.35);
    }
    .brand-title h1 { font-size: 20px; font-weight: 800; color: #fff; letter-spacing: -0.02em; }
    .brand-title p { font-size: 13px; color: var(--text-muted); margin-top: 2px; }
    .header-actions { display: flex; align-items: center; gap: 12px; }
    .status-badge {
      background: rgba(16, 185, 129, 0.12); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4);
      padding: 6px 14px; border-radius: 20px; font-size: 12px; font-weight: 600;
      display: flex; align-items: center; gap: 8px;
    }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; background: #10b981; box-shadow: 0 0 8px #10b981; }

    /* Diagnostic Grid */
    .diag-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
    @media (max-width: 900px) { .diag-grid { grid-template-columns: repeat(2, 1fr); } }
    .diag-card {
      background: var(--card-bg); border: 1px solid var(--border);
      border-radius: 12px; padding: 16px;
    }
    .diag-label { font-size: 11px; text-transform: uppercase; color: var(--text-muted); font-weight: 700; letter-spacing: 0.05em; }
    .diag-val { font-size: 16px; font-weight: 700; color: #fff; margin: 6px 0 2px 0; font-family: var(--font-mono); }
    .diag-meta { font-size: 12px; color: var(--text-muted); }

    /* Controls & Tabs */
    .section-box {
      background: var(--card-bg); border: 1px solid var(--border);
      border-radius: 14px; padding: 22px; margin-bottom: 24px;
    }
    .tabs { display: flex; gap: 10px; border-bottom: 1px solid var(--border); padding-bottom: 14px; margin-bottom: 18px; }
    .tab-btn {
      background: transparent; border: none; color: var(--text-muted); font-size: 13px; font-weight: 600;
      padding: 8px 16px; border-radius: 6px; cursor: pointer; transition: all 0.2s;
    }
    .tab-btn.active { background: rgba(236, 72, 153, 0.15); color: #f472b6; }
    .tab-content { display: none; }
    .tab-content.active { display: block; }

    .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
    @media (max-width: 768px) { .form-grid { grid-template-columns: 1fr; } }
    .field-label { font-size: 12px; font-weight: 600; color: #d1d5db; margin-bottom: 6px; display: block; }
    textarea, select, input {
      width: 100%; background: var(--card-inner); border: 1px solid var(--border);
      border-radius: 8px; color: #fff; padding: 10px 12px; font-family: inherit; font-size: 13px;
    }
    textarea:focus, select:focus, input:focus { outline: none; border-color: #ec4899; }
    textarea { height: 90px; resize: vertical; }

    .btn {
      padding: 10px 20px; border-radius: 8px; font-weight: 600; font-size: 13px;
      cursor: pointer; border: none; transition: all 0.2s; display: inline-flex; align-items: center; gap: 8px;
    }
    .btn-primary { background: #ec4899; color: #fff; }
    .btn-primary:hover { background: #db2777; }
    .btn-preset { background: #1f2937; color: #d1d5db; border: 1px solid #374151; }
    .btn-preset:hover { background: #374151; color: #fff; }

    /* Results */
    .results-area {
      display: none; margin-top: 20px; padding: 20px;
      background: var(--card-inner); border: 1px solid var(--border); border-radius: 12px;
    }
    .decision-badge {
      display: inline-block; padding: 6px 16px; border-radius: 20px;
      font-size: 13px; font-weight: 800; letter-spacing: 0.05em; font-family: var(--font-mono);
      margin-bottom: 14px;
    }
    .dec-ACCEPT { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid #10b981; }
    .dec-ACCEPT_WITH_WARNINGS { background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid #f59e0b; }
    .dec-RETRY_WITH_ALTERNATE_PROVIDER { background: rgba(139, 92, 246, 0.2); color: #c4b5fd; border: 1px solid #8b5cf6; }
    .dec-HOLD_FOR_HUMAN { background: rgba(56, 189, 248, 0.2); color: #38bdf8; border: 1px solid #0284c7; }
    .dec-REJECT { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #ef4444; }

    .score-meter {
      display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin-bottom: 16px;
    }
    @media (max-width: 768px) { .score-meter { grid-template-columns: repeat(2, 1fr); } }
    .score-box { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; padding: 10px; text-align: center; }
    .score-box .s-name { font-size: 11px; color: var(--text-muted); }
    .score-box .s-val { font-size: 16px; font-weight: 800; color: #fff; font-family: var(--font-mono); margin-top: 4px; }

    .issues-table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 12px; }
    .issues-table th { text-align: left; padding: 8px; color: var(--text-muted); border-bottom: 1px solid var(--border); }
    .issues-table td { padding: 8px; border-bottom: 1px solid rgba(255,255,255,0.03); }
    .sev-badge { padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 700; font-family: var(--font-mono); }
    .sev-CRITICAL { background: rgba(239, 68, 68, 0.25); color: #f87171; }
    .sev-MAJOR { background: rgba(245, 158, 11, 0.25); color: #fbbf24; }
    .sev-MINOR { background: rgba(56, 189, 248, 0.25); color: #38bdf8; }
    .sev-INFO { background: rgba(156, 163, 175, 0.2); color: #9ca3af; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="brand">
        <div class="brand-icon">QA</div>
        <div class="brand-title">
          <h1>TalkFlow Translation Quality Agent (Agent 05)</h1>
          <p>Autonomous Meaning Preservation, Data Integrity Gating & Error Classification</p>
        </div>
      </div>
      <div class="header-actions">
        <div class="status-badge"><div class="status-dot"></div><span>ONLINE :8005</span></div>
        <a href="/docs" target="_blank" class="btn btn-preset" style="text-decoration:none; padding:6px 12px;">Swagger</a>
        <a href="/metrics" target="_blank" class="btn btn-preset" style="text-decoration:none; padding:6px 12px;">Metrics</a>
      </div>
    </header>

    <!-- Diagnostics Grid -->
    <div class="diag-grid">
      <div class="diag-card">
        <div class="diag-label">Primary Evaluator</div>
        <div class="diag-val" style="color:#ec4899;">semantic_multilingual</div>
        <div class="diag-meta">Reference-Free Cross-Lingual (<15ms)</div>
      </div>
      <div class="diag-card">
        <div class="diag-label">Reference Evaluator</div>
        <div class="diag-val" style="color:#38bdf8;">sacrebleu / chrF++</div>
        <div class="diag-meta">Corpus & Sentence BLEU v2.6.0</div>
      </div>
      <div class="diag-card">
        <div class="diag-label">Safety Gating</div>
        <div class="diag-val" style="color:#10b981;">HARD GATES ACTIVE</div>
        <div class="diag-meta">Blocks Numbers, Negation & Script Flips</div>
      </div>
      <div class="diag-card">
        <div class="diag-label">Operations Brain</div>
        <div class="diag-val" style="color:#c4b5fd;">OpenAI Agents SDK</div>
        <div class="diag-meta">Ollama (qwen3.5:4b) Out-of-Band</div>
      </div>
    </div>

    <!-- Main Section Box -->
    <div class="section-box">
      <div class="tabs">
        <button class="tab-btn active" onclick="switchTab('playground')">Single Translation Evaluation</button>
        <button class="tab-btn" onclick="switchTab('presets')">Instant Quality Test Presets</button>
        <button class="tab-btn" onclick="switchTab('queue')">Human Review Queue (<span id="queue-count">0</span>)</button>
      </div>

      <!-- Tab 1: Playground -->
      <div id="tab-playground" class="tab-content active">
        <div class="form-grid">
          <div>
            <label class="field-label">Original Source Transcript (Agent 02 / 03):</label>
            <textarea id="src-text" placeholder="e.g. कंपनी अगले महीने ₹12,50,000 का निवेश करेगी।"></textarea>
            <div style="display:flex; gap:10px; margin-top:8px;">
              <select id="src-lang" style="width:140px;">
                <option value="hi" selected>Hindi (hi)</option>
                <option value="en">English (en)</option>
                <option value="mr">Marathi (mr)</option>
                <option value="bn">Bengali (bn)</option>
                <option value="ja">Japanese (ja)</option>
              </select>
            </div>
          </div>
          <div>
            <label class="field-label">Candidate Translation (Agent 04):</label>
            <textarea id="tgt-text" placeholder="e.g. The company will invest ₹12,50,000 next month."></textarea>
            <div style="display:flex; gap:10px; margin-top:8px;">
              <select id="tgt-lang" style="width:140px;">
                <option value="en" selected>English (en)</option>
                <option value="hi">Hindi (hi)</option>
                <option value="mr">Marathi (mr)</option>
                <option value="bn">Bengali (bn)</option>
                <option value="ja">Japanese (ja)</option>
              </select>
            </div>
          </div>
        </div>

        <button class="btn btn-primary" id="btn-eval" onclick="evaluateSingleCandidate()">Evaluate Translation Candidate</button>

        <!-- Evaluation Results Display -->
        <div class="results-area" id="results-area">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <div>
              <span class="decision-badge" id="res-dec">ACCEPT</span>
              <span style="font-size:12px; color:var(--text-muted); margin-left:10px;" id="res-id"></span>
            </div>
            <div style="font-size:12px; font-family:var(--font-mono); color:#a78bfa;" id="res-latency">12.4ms</div>
          </div>

          <div class="score-meter">
            <div class="score-box"><div class="s-name">Overall Quality</div><div class="s-val" id="s-overall">0.96</div></div>
            <div class="score-box"><div class="s-name">Semantic Match</div><div class="s-val" id="s-semantic">0.98</div></div>
            <div class="score-box"><div class="s-name">Data Integrity</div><div class="s-val" id="s-data">1.00</div></div>
            <div class="score-box"><div class="s-name">Completeness</div><div class="s-val" id="s-comp">1.00</div></div>
            <div class="score-box"><div class="s-name">Terminology</div><div class="s-val" id="s-term">1.00</div></div>
          </div>

          <div style="font-weight:700; font-size:12px; margin-bottom:8px; color:#d1d5db;">Detected Quality Issues:</div>
          <table class="issues-table">
            <thead>
              <tr><th>Severity</th><th>Category</th><th>Code</th><th>Description</th></tr>
            </thead>
            <tbody id="issues-body">
              <tr><td colspan="4" style="color:#10b981;">No issues found. Translation passed all safety gates!</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Tab 2: Test Presets -->
      <div id="tab-presets" class="tab-content">
        <p style="font-size:13px; color:var(--text-muted); margin-bottom:16px;">
          Click any preset to verify Agent 05's deterministic gating and error detection:
        </p>
        <div style="display:flex; flex-direction:column; gap:10px;">
          <button class="btn btn-preset" onclick="loadPreset('clean')">
            <strong style="color:#10b981;">[PASS]</strong> Clean Hindi &rarr; English (Amount ₹12,50,000 preserved) &rarr; ACCEPT
          </button>
          <button class="btn btn-preset" onclick="loadPreset('number_corruption')">
            <strong style="color:#ef4444;">[FAIL]</strong> Number Corruption (₹12,50,000 &rarr; ₹1,25,000 single digit drop) &rarr; RETRY / REJECT
          </button>
          <button class="btn btn-preset" onclick="loadPreset('negation_flip')">
            <strong style="color:#ef4444;">[FAIL]</strong> Negation Polarity Reversal ("Do not restart" &rarr; "Restart the server") &rarr; REJECT
          </button>
          <button class="btn btn-preset" onclick="loadPreset('wrong_script')">
            <strong style="color:#ef4444;">[FAIL]</strong> Target Script Mismatch (Requested Marathi, got English ASCII) &rarr; RETRY / REJECT
          </button>
          <button class="btn btn-preset" onclick="loadPreset('temporal_flip')">
            <strong style="color:#f59e0b;">[WARN]</strong> Temporal Anchor Mismatch (Next Month &rarr; Next Year) &rarr; RETRY
          </button>
        </div>
      </div>

      <!-- Tab 3: Review Queue -->
      <div id="tab-queue" class="tab-content">
        <p style="font-size:13px; color:var(--text-muted); margin-bottom:14px;">
          Translations flagged for human review due to ambiguity or experimental language pairs:
        </p>
        <div id="queue-list" style="font-size:13px; color:var(--text-muted);">
          No items currently pending human review.
        </div>
      </div>
    </div>
  </div>

  <script>
    function switchTab(t) {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      event.target.classList.add('active');
      document.getElementById('tab-' + t).classList.add('active');
      if (t === 'queue') fetchQueue();
    }

    async function evaluateSingleCandidate() {
      const src = document.getElementById('src-text').value;
      const tgt = document.getElementById('tgt-text').value;
      const sLang = document.getElementById('src-lang').value;
      const tLang = document.getElementById('tgt-lang').value;
      const btn = document.getElementById('btn-eval');

      if (!src.trim() || !tgt.trim()) {
        alert("Please enter both source transcript and candidate translation.");
        return;
      }

      btn.setAttribute('disabled', 'true');
      btn.innerText = "Evaluating Quality...";

      try {
        const resp = await fetch('/api/v1/quality/evaluate', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            source_text: src,
            target_text: tgt,
            source_lang: sLang,
            target_lang: tLang
          })
        });

        const data = await resp.json();
        document.getElementById('results-area').style.display = 'block';
        const badge = document.getElementById('res-dec');
        badge.innerText = data.decision;
        badge.className = `decision-badge dec-${data.decision}`;
        document.getElementById('res-id').innerText = `ID: ${data.evaluation_id}`;
        document.getElementById('res-latency').innerText = `${data.evaluation_latency_ms} ms`;

        document.getElementById('s-overall').innerText = data.overall_score.toFixed(2);
        document.getElementById('s-semantic').innerText = (data.scores.semantic || 1.0).toFixed(2);
        document.getElementById('s-data').innerText = (data.scores.data_integrity || 1.0).toFixed(2);
        document.getElementById('s-comp').innerText = (data.scores.completeness || 1.0).toFixed(2);
        document.getElementById('s-term').innerText = (data.scores.terminology || 1.0).toFixed(2);

        const tbody = document.getElementById('issues-body');
        tbody.innerHTML = '';
        if (data.issues && data.issues.length > 0) {
          data.issues.forEach(i => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
              <td><span class="sev-badge sev-${i.severity}">${i.severity}</span></td>
              <td>${i.category}</td>
              <td><strong>${i.code}</strong></td>
              <td>${i.description}</td>
            `;
            tbody.appendChild(tr);
          });
        } else {
          tbody.innerHTML = `<tr><td colspan="4" style="color:#10b981; font-weight:600;">&check; Clean evaluation: No data corruptions or meaning reversals detected.</td></tr>`;
        }

      } catch (err) {
        alert("Evaluation failed: " + err.message);
      } finally {
        btn.removeAttribute('disabled');
        btn.innerText = "Evaluate Translation Candidate";
      }
    }

    const PRESETS = {
      clean: {
        src: "कंपनी अगले महीने ₹12,50,000 का निवेश करेगी।",
        tgt: "The company will invest ₹12,50,000 next month.",
        sLang: "hi", tLang: "en"
      },
      number_corruption: {
        src: "कंपनी अगले महीने ₹12,50,000 का निवेश करेगी।",
        tgt: "The company will invest ₹1,25,000 next month.",
        sLang: "hi", tLang: "en"
      },
      negation_flip: {
        src: "Do not restart the server now.",
        tgt: "सर्वर को अभी पुनः आरंभ करें।",
        sLang: "en", tLang: "hi"
      },
      wrong_script: {
        src: "आमचा संघ नवीन प्रकल्पावर चर्चा करेल.",
        tgt: "Our team will discuss the new project.",
        sLang: "mr", tLang: "mr"  // Asked for Marathi, got English
      },
      temporal_flip: {
        src: "कंपनी अगले महीने निवेश करेगी।",
        tgt: "The company will invest next year.",
        sLang: "hi", tLang: "en"
      }
    };

    function loadPreset(key) {
      const p = PRESETS[key];
      document.getElementById('src-text').value = p.src;
      document.getElementById('tgt-text').value = p.tgt;
      document.getElementById('src-lang').value = p.sLang;
      document.getElementById('tgt-lang').value = p.tLang;
      switchTab('playground');
      evaluateSingleCandidate();
    }

    async function fetchQueue() {
      try {
        const resp = await fetch('/api/v1/quality/review-queue');
        const items = await resp.json();
        document.getElementById('queue-count').innerText = items.length;
        const div = document.getElementById('queue-list');
        if (!items || items.length === 0) {
          div.innerHTML = "<p style='color:#10b981;'>Queue is clear. No translations currently held for review.</p>";
          return;
        }
        let html = '';
        items.forEach(it => {
          html += `
            <div style="background:#0b1120; border:1px solid #1f2937; border-radius:8px; padding:12px; margin-bottom:10px;">
              <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
                <span style="font-weight:700; color:#38bdf8;">[${it.source_lang.toUpperCase()} &rarr; ${it.target_lang.toUpperCase()}] Evaluation: ${it.evaluation_id}</span>
                <span class="sev-badge sev-MAJOR">${it.suggested_decision}</span>
              </div>
              <div style="font-size:12px; margin-bottom:4px;"><strong>Source:</strong> ${it.source_text}</div>
              <div style="font-size:12px; margin-bottom:6px;"><strong>Target:</strong> ${it.target_text}</div>
              <div style="font-size:11px; color:#f59e0b;">Reasons: ${it.reasons.join(', ')}</div>
            </div>`;
        });
        div.innerHTML = html;
      } catch (_) {}
    }
    fetchQueue();
  </script>
</body>
</html>
"""

