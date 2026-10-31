"""Interactive Web Dashboard for Agent 07 Audio Synchronization & Delivery."""
from __future__ import annotations

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Agent 07: Audio Synchronization & Delivery | TalkFlow AI</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    @keyframes pulse-subtle {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.6; }
    }
    .animate-pulse-subtle { animation: pulse-subtle 2s infinite ease-in-out; }
  </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen font-sans flex flex-col">
  <!-- Top Navigation -->
  <header class="bg-slate-900 border-b border-slate-800 px-6 py-4 flex items-center justify-between sticky top-0 z-50">
    <div class="flex items-center space-x-3">
      <div class="h-10 w-10 rounded-xl bg-gradient-to-tr from-cyan-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-cyan-500/20">
        <i class="fa-solid fa-volume-high text-white text-lg"></i>
      </div>
      <div>
        <h1 class="text-xl font-bold tracking-tight bg-gradient-to-r from-cyan-400 to-indigo-400 bg-clip-text text-transparent">
          TalkFlow Audio Delivery Agent (Agent 07)
        </h1>
        <p class="text-xs text-slate-400">Jitter Buffering • Conversational Sync • 1-to-N Fan-out • 0x54 Wire Delivery</p>
      </div>
    </div>
    <div class="flex items-center space-x-4">
      <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 animate-pulse-subtle">
        <span class="w-2 h-2 rounded-full bg-emerald-400 mr-2"></span> Active on Port 8007
      </span>
      <a href="/docs" target="_blank" class="px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 transition">
        <i class="fa-solid fa-book mr-1.5 text-cyan-400"></i> API Docs
      </a>
      <a href="/metrics" target="_blank" class="px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 transition">
        <i class="fa-solid fa-chart-line mr-1.5 text-indigo-400"></i> Metrics
      </a>
    </div>
  </header>

  <!-- Main Container -->
  <main class="flex-1 max-w-7xl w-full mx-auto p-6 space-y-6">
    <!-- Pipeline Breadcrumb -->
    <div class="bg-slate-900/60 backdrop-blur border border-slate-800/80 rounded-2xl p-4 flex flex-wrap items-center justify-between gap-3 text-xs">
      <div class="flex items-center space-x-2 text-slate-400">
        <span class="font-semibold text-slate-300">Live Architecture:</span>
        <span class="px-2 py-0.5 rounded bg-slate-800 text-slate-300">01 Audio (8001)</span>
        <i class="fa-solid fa-arrow-right text-slate-600"></i>
        <span class="px-2 py-0.5 rounded bg-slate-800 text-slate-300">02 STT (8002)</span>
        <i class="fa-solid fa-arrow-right text-slate-600"></i>
        <span class="px-2 py-0.5 rounded bg-slate-800 text-slate-300">03 LID (8003)</span>
        <i class="fa-solid fa-arrow-right text-slate-600"></i>
        <span class="px-2 py-0.5 rounded bg-slate-800 text-slate-300">04 MT (8004)</span>
        <i class="fa-solid fa-arrow-right text-slate-600"></i>
        <span class="px-2 py-0.5 rounded bg-slate-800 text-slate-300">05 QA (8005)</span>
        <i class="fa-solid fa-arrow-right text-slate-600"></i>
        <span class="px-2 py-0.5 rounded bg-slate-800 text-slate-300">06 TTS (8006)</span>
        <i class="fa-solid fa-arrow-right text-slate-600"></i>
        <span class="px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 font-bold border border-cyan-500/30">07 Delivery (8007)</span>
      </div>
      <div class="text-xs text-slate-500">Autonomous Cascade Ready</div>
    </div>

    <!-- Live Telemetry KPI Cards -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
      <div class="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-sm">
        <div class="flex items-center justify-between text-slate-400 text-xs font-medium mb-2">
          <span>Ingested Chunks</span>
          <i class="fa-solid fa-cloud-arrow-down text-cyan-400"></i>
        </div>
        <div id="stat-ingested" class="text-3xl font-bold text-white tracking-tight">0</div>
        <div class="text-xs text-slate-500 mt-1">From Agent 06 (TTS)</div>
      </div>
      <div class="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-sm">
        <div class="flex items-center justify-between text-slate-400 text-xs font-medium mb-2">
          <span>Delivered Chunks</span>
          <i class="fa-solid fa-paper-plane text-emerald-400"></i>
        </div>
        <div id="stat-delivered" class="text-3xl font-bold text-emerald-400 tracking-tight">0</div>
        <div class="text-xs text-slate-500 mt-1">0x54 Binary & WebRTC</div>
      </div>
      <div class="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-sm">
        <div class="flex items-center justify-between text-slate-400 text-xs font-medium mb-2">
          <span>Fan-Out Deliveries</span>
          <i class="fa-solid fa-users text-indigo-400"></i>
        </div>
        <div id="stat-fanout" class="text-3xl font-bold text-indigo-400 tracking-tight">0</div>
        <div class="text-xs text-slate-500 mt-1">1-to-N Multiplied Streams</div>
      </div>
      <div class="bg-slate-900/80 border border-slate-800 rounded-2xl p-5 shadow-sm">
        <div class="flex items-center justify-between text-slate-400 text-xs font-medium mb-2">
          <span>Dropped / Stale</span>
          <i class="fa-solid fa-filter text-amber-400"></i>
        </div>
        <div id="stat-dropped" class="text-3xl font-bold text-amber-400 tracking-tight">0</div>
        <div class="text-xs text-slate-500 mt-1">Conversational Freshness</div>
      </div>
    </div>

    <!-- Main 2-Column Section -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Left Column: Operations & Testing -->
      <div class="lg:col-span-2 space-y-6">
        <!-- Audio Simulation Box -->
        <div class="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
          <div class="flex items-center justify-between">
            <h2 class="text-base font-semibold text-white flex items-center">
              <i class="fa-solid fa-bolt mr-2 text-cyan-400"></i> Test Audio Ingestion & Delivery
            </h2>
            <span class="text-xs text-slate-400">Simulate Agent 06 &gt; Agent 07</span>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label class="block text-xs font-medium text-slate-400 mb-1">Room ID</label>
              <input id="input-room-id" type="text" value="room_demo_01" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500">
            </div>
            <div>
              <label class="block text-xs font-medium text-slate-400 mb-1">Speaker ID</label>
              <input id="input-speaker-id" type="text" value="speaker_001" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500">
            </div>
            <div>
              <label class="block text-xs font-medium text-slate-400 mb-1">Target Language</label>
              <select id="input-target-lang" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500">
                <option value="mr">Marathi (mr)</option>
                <option value="hi">Hindi (hi)</option>
                <option value="en">English (en)</option>
                <option value="bn">Bengali (bn)</option>
                <option value="ja">Japanese (ja)</option>
              </select>
            </div>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label class="block text-xs font-medium text-slate-400 mb-1">Chunk Index</label>
              <input id="input-chunk-index" type="number" value="0" min="0" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500">
            </div>
            <div class="flex items-center pt-5 space-x-2">
              <input id="input-is-final" type="checkbox" class="rounded bg-slate-950 border-slate-800 text-cyan-500 focus:ring-0">
              <label for="input-is-final" class="text-xs text-slate-300">Is Final Chunk</label>
            </div>
            <div class="pt-4 flex space-x-2">
              <button onclick="sendTestChunk()" class="flex-1 bg-cyan-600 hover:bg-cyan-500 text-white font-semibold text-xs py-2 px-3 rounded-xl transition shadow-lg shadow-cyan-600/20 flex items-center justify-center">
                <i class="fa-solid fa-play mr-1.5"></i> Ingest Chunk
              </button>
              <button onclick="triggerBargeIn()" class="bg-rose-600/20 hover:bg-rose-600 text-rose-300 hover:text-white border border-rose-500/30 text-xs font-semibold py-2 px-3 rounded-xl transition flex items-center justify-center" title="Barge-in Interruption">
                <i class="fa-solid fa-hand mr-1"></i> Flush
              </button>
            </div>
          </div>

          <div id="test-result-box" class="hidden bg-slate-950 border border-slate-800/80 rounded-xl p-3 text-xs font-mono text-slate-300"></div>
        </div>

        <!-- Participants Management Box -->
        <div class="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
          <div class="flex items-center justify-between">
            <h2 class="text-base font-semibold text-white flex items-center">
              <i class="fa-solid fa-users mr-2 text-indigo-400"></i> Meeting Participants & Routes
            </h2>
            <button onclick="registerSampleParticipants()" class="text-xs text-indigo-400 hover:text-indigo-300 transition font-medium">
              <i class="fa-solid fa-user-plus mr-1"></i> Load Sample Meeting Seats
            </button>
          </div>

          <div class="overflow-x-auto">
            <table class="w-full text-left text-xs">
              <thead>
                <tr class="border-b border-slate-800 text-slate-400 font-medium">
                  <th class="pb-2">Participant</th>
                  <th class="pb-2">Room</th>
                  <th class="pb-2">Hear Lang</th>
                  <th class="pb-2">Playback Mode</th>
                  <th class="pb-2">Wire Extension</th>
                  <th class="pb-2 text-right">Status</th>
                </tr>
              </thead>
              <tbody id="participants-table-body" class="divide-y divide-slate-800/50 text-slate-300">
                <tr>
                  <td colspan="6" class="py-4 text-center text-slate-500">No participants registered in current room. Click 'Load Sample Meeting Seats' above.</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Real-time Ingestion Event Feed -->
        <div class="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-sm space-y-3">
          <div class="flex items-center justify-between">
            <h2 class="text-base font-semibold text-white flex items-center">
              <i class="fa-solid fa-list-check mr-2 text-emerald-400"></i> Event Audit Trail
            </h2>
            <span class="text-xs text-slate-500">Real-time Ingestion & Fan-out</span>
          </div>
          <div id="events-log" class="h-44 overflow-y-auto space-y-2 pr-2 text-xs font-mono">
            <div class="text-slate-500 italic">Listening for audio chunk arrivals and deliveries...</div>
          </div>
        </div>
      </div>

      <!-- Right Column: Diagnostic Brain & Wire Specifications -->
      <div class="space-y-6">
        <!-- Brain Assistant Box -->
        <div class="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
          <div class="flex items-center justify-between">
            <h2 class="text-base font-semibold text-white flex items-center">
              <i class="fa-solid fa-brain mr-2 text-purple-400"></i> Delivery Diagnostic Brain
            </h2>
            <span class="text-xs bg-purple-500/10 text-purple-300 border border-purple-500/20 px-2 py-0.5 rounded-full font-medium">
              Expert Mode
            </span>
          </div>
          <p class="text-xs text-slate-400">Ask about jitter buffering, 0x54 wire framing, ducking, barge-in, or timeline synchronicity.</p>

          <div class="space-y-2">
            <input id="brain-input" type="text" placeholder="e.g. How does 0x54 binary wire format work?" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-purple-500">
            <div class="flex space-x-2">
              <button onclick="askBrain()" class="flex-1 bg-purple-600 hover:bg-purple-500 text-white font-semibold text-xs py-2 px-3 rounded-xl transition shadow-lg shadow-purple-600/20 flex items-center justify-center">
                <i class="fa-solid fa-sparkles mr-1.5"></i> Ask Brain
              </button>
            </div>
          </div>

          <div id="brain-response-box" class="hidden bg-slate-950 border border-slate-800/80 rounded-xl p-3 text-xs text-slate-300 leading-relaxed max-h-56 overflow-y-auto"></div>
        </div>

        <!-- Wire Spec Reference Card -->
        <div class="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-sm space-y-3">
          <h3 class="text-xs font-bold uppercase tracking-wider text-slate-400">
            <i class="fa-solid fa-code mr-1.5 text-cyan-400"></i> TalkFlow 0x54 Frame Layout
          </h3>
          <div class="bg-slate-950 p-3 rounded-xl border border-slate-800/80 text-[11px] font-mono text-slate-400 space-y-1">
            <div class="text-cyan-400">0x00: 0x54 ('T') Magic Tag</div>
            <div>0x01..0x10: 16-byte Short UUID</div>
            <div>0x11: uint8 Lang Len (L)</div>
            <div>0x12..(0x12+L-1): UTF-8 Lang</div>
            <div class="text-indigo-400">0x12+L: 0x01 Extension Marker</div>
            <div class="text-indigo-400">Next 4 bytes: uint32 Chunk Idx</div>
            <div class="text-emerald-400">Remainder: Raw Audio Payload</div>
          </div>
        </div>

        <!-- Feedback Loop Safety Card -->
        <div class="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-sm space-y-2">
          <h3 class="text-xs font-bold uppercase tracking-wider text-slate-400">
            <i class="fa-solid fa-shield-halved mr-1.5 text-emerald-400"></i> Multi-Tenant & Loop Safety
          </h3>
          <p class="text-xs text-slate-400 leading-relaxed">
            Speaker exclusion is strictly enforced in multi-user rooms. Synthetic chunks carry <code class="text-cyan-300">synthetic=true</code> to prevent microphone echo loops into Agent 01/02 STT.
          </p>
        </div>
      </div>
    </div>
  </main>

  <script>
    // State
    let currentRoomId = "room_demo_01";

    // Refresh telemetry
    async function refreshTelemetry() {
      try {
        const res = await fetch("/api/v1/delivery/stats");
        if (res.ok) {
          const data = await res.json();
          document.getElementById("stat-ingested").innerText = data.total_ingested_chunks || 0;
          document.getElementById("stat-delivered").innerText = data.total_delivered_chunks || 0;
          document.getElementById("stat-fanout").innerText = data.total_fanout_deliveries || 0;
          document.getElementById("stat-dropped").innerText = data.total_dropped_chunks || 0;
        }
      } catch (e) {
        console.error("Telemetry fetch error:", e);
      }
    }

    async function loadParticipants() {
      try {
        const res = await fetch("/api/v1/rooms/" + currentRoomId);
        if (res.ok) {
          const room = await res.json();
          const tbody = document.getElementById("participants-table-body");
          if (!room.participants || room.participants.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="py-4 text-center text-slate-500">No participants registered in current room. Click Load Sample Meeting Seats.</td></tr>';
            return;
          }
          tbody.innerHTML = room.participants.map(p => `
            <tr class="hover:bg-slate-800/30">
              <td class="py-2.5 font-medium text-white flex items-center space-x-2">
                <span class="w-6 h-6 rounded-full bg-slate-800 flex items-center justify-center text-[10px] text-cyan-400 font-bold">
                  ${p.display_name.charAt(0)}
                </span>
                <span>${p.display_name} <span class="text-slate-500 font-normal">(${p.participant_id})</span></span>
              </td>
              <td class="py-2.5 text-slate-400">${p.room_id}</td>
              <td class="py-2.5"><span class="px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-300 font-mono font-semibold">${p.hear_lang}</span></td>
              <td class="py-2.5 capitalize text-slate-300">${p.playback_mode}</td>
              <td class="py-2.5 font-mono text-[11px] text-slate-400">${p.supports_tts_chunk_index ? 'Enabled (0x01)' : 'Legacy'}</td>
              <td class="py-2.5 text-right"><span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/10 text-emerald-400">Connected</span></td>
            </tr>
          `).join('');
        }
      } catch (e) {
        console.error("Failed to load participants:", e);
      }
    }

    async function registerSampleParticipants() {
      const seats = [
        { participant_id: "user_marathi", room_id: currentRoomId, display_name: "Aarav (Marathi)", hear_lang: "mr", playback_mode: "translated" },
        { participant_id: "user_hindi", room_id: currentRoomId, display_name: "Pooja (Hindi)", hear_lang: "hi", playback_mode: "translated" },
        { participant_id: "user_english", room_id: currentRoomId, display_name: "John (English)", hear_lang: "en", playback_mode: "both" },
        { participant_id: "speaker_001", room_id: currentRoomId, display_name: "Speaker Aman", hear_lang: "hi", playback_mode: "original" },
      ];

      for (const s of seats) {
        await fetch("/api/v1/rooms/participants", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(s)
        });
      }
      appendEventLog(`Registered ${seats.length} sample meeting seats in ${currentRoomId}`);
      await loadParticipants();
    }

    async function sendTestChunk() {
      const roomId = document.getElementById("input-room-id").value.trim();
      const speakerId = document.getElementById("input-speaker-id").value.trim();
      const targetLang = document.getElementById("input-target-lang").value;
      const chunkIdx = parseInt(document.getElementById("input-chunk-index").value, 10);
      const isFinal = document.getElementById("input-is-final").checked;

      // Dummy 100ms synthetic audio chunk (16-bit 24kHz mono PCM = 4800 bytes)
      const dummyPcm = new Uint8Array(4800);
      let binary = '';
      for (let i = 0; i < dummyPcm.byteLength; i++) {
        binary += String.fromCharCode(dummyPcm[i]);
      }
      const b64 = btoa(binary);

      const payload = {
        session_id: roomId,
        conversation_id: roomId,
        speaker_id: speakerId,
        segment_id: "seg_" + Math.random().toString(36).substring(2, 10),
        target_lang: targetLang,
        chunk_index: chunkIdx,
        is_final_chunk: isFinal,
        duration_ms: 100.0,
        audio_base64: b64,
        synthetic: true,
        audio_origin: "synthetic_tts",
        created_at: Date.now() / 1000
      };

      try {
        const res = await fetch("/api/v1/delivery/chunks", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        const box = document.getElementById("test-result-box");
        box.classList.remove("hidden");
        box.innerHTML = `<span class="text-cyan-400 font-bold">[${data.status.toUpperCase()}]</span> Action: ${data.action_taken} • Recipients: ${data.recipients_count} • Latency: ${data.latency_ms.toFixed(1)}ms`;
        appendEventLog(`Ingested chunk #${chunkIdx} (${targetLang}) > ${data.status} to ${data.recipients_count} listeners`);
        await refreshTelemetry();
        // Increment chunk index automatically
        document.getElementById("input-chunk-index").value = chunkIdx + 1;
      } catch (e) {
        appendEventLog(`Error ingesting chunk: ${e.message}`);
      }
    }

    async function triggerBargeIn() {
      const roomId = document.getElementById("input-room-id").value.trim();
      const speakerId = document.getElementById("input-speaker-id").value.trim();
      try {
        const res = await fetch("/api/v1/delivery/cancel", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            room_id: roomId,
            speaker_id: speakerId,
            reason: "manual_barge_in"
          })
        });
        const data = await res.json();
        appendEventLog(`[BARGE-IN FLUSH] Room ${roomId} flushed ${data.flushed_chunks} queued chunks`);
        await refreshTelemetry();
      } catch (e) {
        appendEventLog(`Barge-in error: ${e.message}`);
      }
    }

    async function askBrain() {
      const q = document.getElementById("brain-input").value.trim();
      if (!q) return;
      const box = document.getElementById("brain-response-box");
      box.classList.remove("hidden");
      box.innerHTML = '<span class="text-purple-400 animate-pulse"><i class="fa-solid fa-spinner fa-spin mr-1"></i> Consulting Agent 07 Brain...</span>';

      try {
        const res = await fetch("/api/v1/brain/query", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: q })
        });
        const data = await res.json();
        box.innerHTML = `
          <div class="text-purple-300 font-semibold mb-1 flex items-center justify-between">
            <span>Agent 07 Brain Analysis</span>
            <span class="text-[10px] text-slate-500 uppercase font-mono">${data.source}</span>
          </div>
          <div class="text-slate-200">${data.answer.replace(/\\n/g, '<br>')}</div>
        `;
      } catch (e) {
        box.innerHTML = `<span class="text-rose-400">Brain error: ${e.message}</span>`;
      }
    }

    function appendEventLog(msg) {
      const log = document.getElementById("events-log");
      const time = new Date().toLocaleTimeString();
      const el = document.createElement("div");
      el.className = "text-slate-300 bg-slate-950/60 p-1.5 rounded border border-slate-800/50";
      el.innerHTML = `<span class="text-slate-500 mr-2">[${time}]</span> ${msg}`;
      log.prepend(el);
    }

    // Startup
    setInterval(refreshTelemetry, 2500);
    window.addEventListener("DOMContentLoaded", () => {
      refreshTelemetry();
      loadParticipants();
    });
  </script>
</body>
</html>
"""

