"""Interactive Web Dashboard for Agent 06 (Voice Generation Agent)."""
from __future__ import annotations

from fastapi.responses import HTMLResponse


def get_dashboard_html() -> HTMLResponse:
    """Return responsive dark-themed dashboard HTML."""
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>TalkFlow Agent 06 — Voice Generation Agent (TTS)</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    :root {
      --bg: #0d1117;
      --card-bg: #161b22;
      --border: #30363d;
      --text: #c9d1d9;
      --text-bright: #f0f6fc;
      --accent: #58a6ff;
      --accent-green: #3fb950;
      --accent-orange: #d29922;
      --accent-red: #f85149;
      --accent-purple: #bc8cff;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background-color: var(--bg); color: var(--text); padding: 24px; }
    header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 24px; }
    .title-area h1 { font-size: 24px; color: var(--text-bright); display: flex; align-items: center; gap: 10px; }
    .badge { font-size: 11px; padding: 4px 8px; border-radius: 12px; font-weight: bold; text-transform: uppercase; }
    .badge-live { background: rgba(63, 185, 80, 0.2); color: var(--accent-green); border: 1px solid var(--accent-green); }
    .badge-port { background: rgba(88, 166, 255, 0.2); color: var(--accent); border: 1px solid var(--accent); }
    .grid { display: grid; grid-template-columns: 1.2fr 1fr; gap: 20px; }
    .card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px; padding: 18px; margin-bottom: 20px; }
    .card h2 { font-size: 16px; color: var(--text-bright); margin-bottom: 14px; border-bottom: 1px solid var(--border); padding-bottom: 8px; }
    label { display: block; font-size: 13px; font-weight: 600; margin-bottom: 6px; color: var(--text-bright); }
    input, select, textarea { width: 100%; background: #0d1117; border: 1px solid var(--border); color: var(--text-bright); padding: 9px 12px; border-radius: 6px; font-size: 14px; margin-bottom: 14px; }
    textarea { resize: vertical; min-height: 80px; }
    .btn-row { display: flex; gap: 10px; margin-top: 8px; }
    button { background: #238636; color: white; border: none; padding: 10px 18px; border-radius: 6px; font-size: 14px; font-weight: 600; cursor: pointer; transition: 0.2s; }
    button:hover { background: #2ea043; }
    button.btn-secondary { background: #21262d; border: 1px solid var(--border); color: var(--text-bright); }
    button.btn-secondary:hover { background: #30363d; }
    button.btn-danger { background: #da3633; }
    button.btn-danger:hover { background: #f85149; }
    .audio-player-box { background: #0d1117; border: 1px solid var(--border); border-radius: 6px; padding: 14px; margin-top: 14px; }
    audio { width: 100%; height: 40px; margin-top: 8px; outline: none; }
    .metrics-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 14px; }
    .metric-pill { background: #0d1117; border: 1px solid var(--border); border-radius: 6px; padding: 10px; text-align: center; }
    .metric-val { font-size: 18px; font-weight: bold; color: var(--accent-green); }
    .metric-lbl { font-size: 11px; color: var(--text); margin-top: 4px; }
    .log-box { background: #000; border: 1px solid var(--border); border-radius: 6px; padding: 12px; font-family: monospace; font-size: 12px; color: #7ee787; height: 260px; overflow-y: auto; white-space: pre-wrap; }
    .voices-table { width: 100%; border-collapse: collapse; font-size: 12px; }
    .voices-table th, .voices-table td { padding: 8px; text-align: left; border-bottom: 1px solid var(--border); }
    .voices-table th { color: var(--text-bright); background: #0d1117; }
  </style>
</head>
<body>
  <header>
    <div class="title-area">
      <h1>TalkFlow Agent 06 — Voice Generation Agent (TTS)</h1>
      <div style="margin-top: 6px; display: flex; gap: 8px;">
        <span class="badge badge-live">Live Autonomous Agent</span>
        <span class="badge badge-port">Port 8006</span>
        <span class="badge" style="background:#1f2937; color:#9ca3af; border:1px solid #374151;">Synthetic Flag Enforced</span>
      </div>
    </div>
    <div style="font-size: 12px; text-align: right; color: #8b949e;">
      Pipeline: Agent 04 (MT) &rarr; Agent 05 (QA) &rarr; <b>Agent 06 (TTS)</b> &rarr; Agent 07 (Sync)
    </div>
  </header>

  <div class="grid">
    <div>
      <!-- Live Synthesis Testing Card -->
      <div class="card">
        <h2>Live Speech Synthesis & Quality Gate Verification</h2>
        
        <label for="txtTarget">Approved Translated Text</label>
        <textarea id="txtTarget">TalkFlow real-time multilingual communication platform converts approved text to natural speech.</textarea>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
          <div>
            <label for="selLang">Target Language</label>
            <select id="selLang" onchange="updatePresetText()">
              <optgroup label="🇮🇳 Indian Regional Languages">
                <option value="hi" selected>Hindi (hi-IN) - हिन्दी</option>
                <option value="mr">Marathi (mr-IN) - मराठी</option>
                <option value="bn">Bengali (bn-BD/IN) - বাংলা</option>
                <option value="gu">Gujarati (gu-IN) - ગુજરાતી</option>
                <option value="ta">Tamil (ta-IN) - தமிழ்</option>
                <option value="te">Telugu (te-IN) - తెలుగు</option>
                <option value="kn">Kannada (kn-IN) - ಕನ್ನಡ</option>
                <option value="ml">Malayalam (ml-IN) - മലയാളം</option>
                <option value="pa">Punjabi (pa-IN) - ਪੰਜਾਬੀ</option>
                <option value="ur">Urdu (ur-PK) - اردو</option>
              </optgroup>
              <optgroup label="🌍 Global International Languages">
                <option value="en">English (en-US / en-IN)</option>
                <option value="es">Spanish (es-ES / es-MX) - Español</option>
                <option value="fr">French (fr-FR) - Français</option>
                <option value="de">German (de-DE) - Deutsch</option>
                <option value="ja">Japanese (ja-JP) - 日本語</option>
                <option value="zh">Chinese (zh-CN) - 简体中文</option>
                <option value="ar">Arabic (ar-SA) - العربية</option>
                <option value="ru">Russian (ru-RU) - Русский</option>
                <option value="pt">Portuguese (pt-BR) - Português</option>
                <option value="it">Italian (it-IT) - Italiano</option>
                <option value="ko">Korean (ko-KR) - 한국어</option>
              </optgroup>
            </select>
          </div>
          <div>
            <label for="selGate">Agent 05 Gate Decision</label>
            <select id="selGate" onchange="updateGateWarning()">
              <option value="ACCEPT">ACCEPT (Passed Gate)</option>
              <option value="ACCEPT_WITH_WARNINGS">ACCEPT_WITH_WARNINGS (Passed Gate)</option>
              <option value="REJECT">REJECT (Must Block Synthesis)</option>
              <option value="HOLD_FOR_HUMAN">HOLD_FOR_HUMAN (Must Block)</option>
            </select>
          </div>
        </div>

        <div id="gateWarningBox" style="display:none; padding: 8px 12px; border-radius: 6px; font-size: 12px; margin-bottom: 12px; background: rgba(248, 81, 73, 0.15); border: 1px solid #f85149; color: #ff7b72;">
          <b>Gate Block Policy:</b> Agent 06 strictly prohibits synthesizing audio for translations flagged as REJECT or HOLD_FOR_HUMAN. Submitting this request will result in HTTP 422 to protect listeners from unapproved, corrupted, or hallucinated speech.
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
          <div>
            <label for="rngScore">Quality Score (<span id="scoreVal">0.95</span>)</label>
            <input type="range" id="rngScore" min="0" max="1" step="0.05" value="0.95" oninput="document.getElementById('scoreVal').innerText=this.value">
          </div>
          <div>
            <label for="selVoice">Voice Selection (Language-Filtered)</label>
            <select id="selVoice">
              <option value="">(Auto Selection via 5-Tier Fallback)</option>
            </select>
          </div>
        </div>

        <div class="btn-row">
          <button onclick="synthesize()">Synthesize Speech</button>
          <button class="btn-secondary" onclick="simulateAgent05()">Simulate Agent 05 Handoff</button>
          <button class="btn-danger" onclick="cancelSynthesis()">Barge-in / Cancel</button>
        </div>

        <!-- Audio Player & Metrics -->
        <div class="audio-player-box" id="playerBox" style="display: none;">
          <label style="color: var(--accent-green); font-size: 13px;">Generated Audio Playback</label>
          <audio id="audioElement" controls></audio>
          
          <div class="metrics-grid">
            <div class="metric-pill">
              <div class="metric-val" id="metricDuration">--</div>
              <div class="metric-lbl">Duration</div>
            </div>
            <div class="metric-pill">
              <div class="metric-val" id="metricLatency">--</div>
              <div class="metric-lbl">Latency</div>
            </div>
            <div class="metric-pill">
              <div class="metric-val" id="metricProvider">--</div>
              <div class="metric-lbl">Provider / Voice</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Operational Reasoning Card -->
      <div class="card">
        <h2>Operational Brain Diagnostics (Ollama)</h2>
        <div style="display: flex; gap: 10px;">
          <input type="text" id="brainPrompt" placeholder="Ask Agent 06 Brain (e.g. Why was DevTone chosen for Marathi?)" value="Explain how Agent 06 enforces Agent 05 quality gate validation.">
          <button class="btn-secondary" style="white-space: nowrap;" onclick="askBrain()">Ask Brain</button>
        </div>
        <div id="brainAnswer" style="background:#0d1117; border:1px solid var(--border); border-radius:6px; padding:10px; font-size:13px; min-height:50px; color:#c9d1d9;">Awaiting query...</div>
      </div>
    </div>

    <div>
      <!-- Live Log Box -->
      <div class="card">
        <h2>Real-Time Agent Events & Wire Framing Log</h2>
        <div class="log-box" id="logBox">[SYSTEM] Agent 06 Voice Generation Agent Initialized. Ready on port 8006.</div>
      </div>

      <!-- Voice Registry Card -->
      <div class="card">
        <h2>Registered Voice Capabilities</h2>
        <div style="max-height: 280px; overflow-y: auto;">
          <table class="voices-table">
            <thead>
              <tr>
                <th>Voice ID</th>
                <th>Lang</th>
                <th>Provider</th>
                <th>Type</th>
              </tr>
            </thead>
            <tbody id="voicesTbody">
              <tr><td colspan="4" style="text-align:center;">Loading voices...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>

  <script>
    function log(msg) {
      const b = document.getElementById('logBox');
      const time = new Date().toLocaleTimeString();
      b.innerText += `\\n[${time}] ${msg}`;
      b.scrollTop = b.scrollHeight;
    }

    const presets = {
      hi: "आज हम अपने नए AI प्रोजेक्ट के बारे में चर्चा करेंगे।",
      mr: "आज आपण आपल्या नवीन AI प्रकल्पाबद्दल चर्चा करू.",
      bn: "আজ আমরা আমাদের নতুন এআই প্রজেক্ট নিয়ে আলোচনা করব।",
      gu: "આજે આપણે અમારા નવા AI પ્રોજેક્ટ વિશે ચર્ચા કરીશું.",
      ta: "இன்று நமது புதிய செயற்கை நுண்ணறிவு திட்டத்தை பற்றி விவாதிப்போம்.",
      te: "ఈ రోజు మన కొత్త ఆర్టిఫిషియల్ ఇంటెలిజెన్స్ ప్రాజెక్ట్ గురించి చర్చిద్దాం.",
      kn: "ಇಂದು ನಾವು ನಮ್ಮ ಹೊಸ ಕೃತಕ ಬುದ್ಧಿಮತ್ತೆ ಯೋಜನೆಯ ಬಗ್ಗೆ ಚರ್ಚಿಸೋಣ.",
      ml: "ഇന്ന് നമ്മുടെ പുതിയ കൃത്രിമ ബുദ്ധി പദ്ധതിയെക്കുറിച്ച് സംസാരിക്കാം.",
      pa: "ਅੱਜ ਅਸੀਂ ਆਪਣੇ ਨਵੇਂ ਆਰਟੀਫੀਸ਼ੀਅਲ ਇੰਟੈਲੀਜੈਂਸ ਪ੍ਰੋਜੈਕਟ ਬਾਰੇ ਚਰਚਾ ਕਰਾਂਗੇ।",
      ur: "آج ہم اپنے نئے مصنوعی ذہانت کے منصوبے پر بات کریں گے۔",
      en: "TalkFlow real-time multilingual communication platform converts approved text to natural speech.",
      es: "Hoy hablaremos sobre nuestro nuevo proyecto de inteligencia artificial.",
      fr: "Aujourd'hui, nous allons discuter de notre nouveau projet d'intelligence artificielle.",
      de: "Heute werden wir über unser neues Projekt für künstliche Intelligenz sprechen.",
      ja: "本日、新しいAIプロジェクトについて議論します。",
      zh: "今天我们将讨论我们全新的人工智能项目。",
      ar: "اليوم سنناقش مشروعنا الجديد في مجال الذكاء الاصطناعي.",
      ru: "Сегодня мы обсудим наш новый проект в области искусственного интеллекта.",
      pt: "Hoje falaremos sobre o nosso novo projeto de inteligência artificial.",
      it: "Oggi parleremo del nostro nuovo progetto di intelligenza artificiale.",
      ko: "오늘 우리는 새로운 인공지능 프로젝트에 대해 논의할 것입니다."
    };

    let registeredVoices = [];

    function updateGateWarning() {
      const gate = document.getElementById('selGate').value;
      const box = document.getElementById('gateWarningBox');
      if (gate === 'REJECT' || gate === 'HOLD_FOR_HUMAN') {
        box.style.display = 'block';
      } else {
        box.style.display = 'none';
      }
    }

    function updateVoiceOptions(lang) {
      const selVoice = document.getElementById('selVoice');
      selVoice.innerHTML = '<option value="">(Auto Selection via 5-Tier Fallback)</option>';
      const langClean = (lang || '').toLowerCase().split('-')[0].split('_')[0];
      const compatibleVoices = registeredVoices.filter(v => {
        const vLang = (v.language || '').toLowerCase().split('-')[0].split('_')[0];
        return vLang === langClean || v.language === '*' || v.language === 'all';
      });
      compatibleVoices.forEach(v => {
        const opt = document.createElement('option');
        opt.value = v.voice_id;
        const provLabel = v.provider === 'edge_tts' ? 'Neural High-Fidelity' : v.provider;
        opt.innerText = `${v.name || v.voice_id} [${provLabel}]`;
        selVoice.appendChild(opt);
      });
      selVoice.value = "";
    }

    function updatePresetText() {
      const lang = document.getElementById('selLang').value;
      if (presets[lang]) {
        document.getElementById('txtTarget').value = presets[lang];
      }
      updateVoiceOptions(lang);
    }

    async function loadVoices() {
      try {
        const res = await fetch('/api/v1/tts/voices');
        const data = await res.json();
        registeredVoices = data.voices || [];
        const tbody = document.getElementById('voicesTbody');
        tbody.innerHTML = '';
        registeredVoices.forEach(v => {
          const tr = document.createElement('tr');
          tr.innerHTML = `<td><b>${v.voice_id}</b></td><td>${v.language}</td><td>${v.provider}</td><td>${v.is_local ? 'Local' : 'Cloud'}</td>`;
          tbody.appendChild(tr);
        });
        updateVoiceOptions(document.getElementById('selLang').value);
        updatePresetText();
      } catch(e) {
        log('Failed to fetch voices: ' + e);
      }
    }
    loadVoices();

    async function synthesize() {
      const text = document.getElementById('txtTarget').value;
      const lang = document.getElementById('selLang').value;
      const gate = document.getElementById('selGate').value;
      const score = parseFloat(document.getElementById('rngScore').value);
      const voice = document.getElementById('selVoice').value || null;

      log(`[SYNTH] Requesting synthesis for lang='${lang}', gate='${gate}', score=${score}...`);

      try {
        const res = await fetch('/api/v1/tts/synthesize', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            text: text,
            target_language: lang,
            quality_decision: gate,
            quality_score: score,
            requested_voice_id: voice,
            conversation_id: 'conv_demo_01',
            segment_id: 'seg_' + Date.now()
          })
        });

        const data = await res.json();
        if (!res.ok) {
          log(`[GATE BLOCKED] Error ${res.status}: ${data.detail || JSON.stringify(data)}`);
          return;
        }

        log(`[SUCCESS] Generated audio in ${data.generation_latency_ms.toFixed(1)}ms. Provider: ${data.provider}, Voice: ${data.voice_id}`);
        
        // Show player
        document.getElementById('playerBox').style.display = 'block';
        const audioEl = document.getElementById('audioElement');
        audioEl.src = 'data:audio/wav;base64,' + data.audio_base64;
        audioEl.play().catch(e => log('Autoplay note: ' + e));

        document.getElementById('metricDuration').innerText = (data.duration_ms / 1000).toFixed(2) + 's';
        document.getElementById('metricLatency').innerText = data.generation_latency_ms.toFixed(0) + 'ms';
        document.getElementById('metricProvider').innerText = `${data.provider}/${data.voice_id}`;
      } catch(e) {
        log(`[ERROR] Synthesis request failed: ${e}`);
      }
    }

    async function simulateAgent05() {
      const text = document.getElementById('txtTarget').value;
      const lang = document.getElementById('selLang').value;
      const segId = 'seg_agent05_' + Date.now();

      log(`[AGENT 05 &rarr; 06] Simulating incoming quality.assessment.final webhook for segment ${segId}...`);

      try {
        const res = await fetch('/api/v1/tts/segment', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            evaluation_id: 'eval_' + segId,
            candidate_hash: 'hash_demo_123',
            session_id: 'sess_live_call',
            conversation_id: 'conv_live_call',
            segment_id: segId,
            translation_id: 'trans_' + segId,
            source_lang: 'hi',
            target_lang: lang,
            source_text: 'आज हम अपने नए AI प्रोजेक्ट के बारे में चर्चा करेंगे।',
            target_text: text,
            decision: 'ACCEPT',
            overall_score: 0.96,
            is_safe_for_voice: true
          })
        });

        const data = await res.json();
        if (res.ok) {
          log(`[HANDOFF COMPLETE] Segment synthesized and forwarded to Agent 07 publisher. Latency: ${data.generation_latency_ms.toFixed(1)}ms`);
          document.getElementById('playerBox').style.display = 'block';
          document.getElementById('audioElement').src = 'data:audio/wav;base64,' + data.audio_base64;
          document.getElementById('metricDuration').innerText = (data.duration_ms / 1000).toFixed(2) + 's';
          document.getElementById('metricLatency').innerText = data.generation_latency_ms.toFixed(0) + 'ms';
          document.getElementById('metricProvider').innerText = `${data.provider}/${data.voice_id}`;
        } else {
          log(`[ERROR] Agent 05 handoff error: ${JSON.stringify(data)}`);
        }
      } catch(e) {
        log(`[ERROR] Webhook simulation failed: ${e}`);
      }
    }

    async function cancelSynthesis() {
      log('[CANCEL] Emitting barge-in interruption signal...');
      try {
        const res = await fetch('/api/v1/tts/cancel', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            session_id: 'sess_live_call',
            reason: 'barge_in_interruption'
          })
        });
        const data = await res.json();
        log(`[CANCELLED] ${data.message}`);
      } catch(e) {
        log(`[ERROR] Cancellation failed: ${e}`);
      }
    }

    async function askBrain() {
      const q = document.getElementById('brainPrompt').value;
      const ans = document.getElementById('brainAnswer');
      ans.innerText = 'Consulting Agent 06 Brain...';
      try {
        const res = await fetch('/api/v1/tts/brain/query', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ prompt: q })
        });
        const data = await res.json();
        ans.innerText = data.response;
      } catch(e) {
        ans.innerText = 'Brain query error: ' + e;
      }
    }
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)

