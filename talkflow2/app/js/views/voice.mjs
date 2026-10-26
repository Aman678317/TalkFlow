import { apiPost, esc, toast, download, fillLangSelect, humanError, fmtClock, bcp47 } from "../api.mjs";
import { getKey } from "../vault.mjs";
import { toSrt, toVtt, toTxt, toJson } from "/engine/subtitles.mjs";

const PROV_KEY = "talkflow.provider";
const providerId = () => (localStorage.getItem(PROV_KEY) === "deepl" ? "deepl" : "local");

export function render(root) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  root.innerHTML = `
  <div class="view">
    <h2 class="view-title">Voice — real-time translate &amp; subtitles</h2>
    <div class="banner warn">Headphone mode advised — spoken translations can be picked up again by the microphone and create an echo loop.</div>
    <div class="card voice-card">
      <div class="voice-bar">
        <span class="field-lbl">Speak</span>
        <select id="v-speak" aria-label="Language you speak"></select>
        <span class="muted">→</span>
        <select id="v-tgt" aria-label="Translation target language"></select>
        <span class="chip" id="v-provider">provider: Demo</span>
        <span class="spacer"></span>
        <button id="v-mic" class="mic-btn" type="button">&#9679; Start listening</button>
      </div>
      <div id="v-key-hint" class="warn-text" hidden></div>
      <div id="v-stage" class="stage">
        <span id="v-status" class="stage-status">Idle — press the button to start speech recognition.</span>
        <div class="captions" hidden>
          <div id="v-concluded" class="concluded"></div>
          <div id="v-target-line" class="caption-target"></div>
          <div id="v-tentative" class="tentative"></div>
        </div>
      </div>
      <div id="v-unsupported" class="banner fail" hidden>Speech recognition is unavailable here (webkitSpeechRecognition missing). Use Chrome or Edge for live voice; all other features still work.</div>
      <div class="voice-foot">
        <label class="check"><input type="checkbox" id="v-incl-src" checked> exports include source (“source / target”)</label>
        <span class="spacer"></span>
        <button id="v-clear" class="btn ghost sm" type="button">Clear transcript</button>
        <button class="btn ghost sm xexport" data-fmt="srt" type="button">Export SRT</button>
        <button class="btn ghost sm xexport" data-fmt="vtt" type="button">Export VTT</button>
        <button class="btn ghost sm xexport" data-fmt="txt" type="button">Export TXT</button>
        <button class="btn ghost sm xexport" data-fmt="json" type="button">Export JSON</button>
      </div>
    </div>
    <div class="card">
      <div class="table-scroll"><table class="table transcript">
        <thead><tr><th>#</th><th>Time</th><th>Source (spoken)</th><th>Target (translated)</th><th></th></tr></thead>
        <tbody id="v-rows"></tbody>
      </table></div>
      <div id="v-empty" class="empty">No transcript yet — final spoken phrases become rows as you talk.</div>
    </div>
  </div>`;

  const $ = (id) => root.querySelector("#" + id);
  const state = {
    phase: "idle", // idle | listening
    t0: 0,
    lastEnd: 0,
    pendingStart: null,
    segments: [],
    index: 0,
    rec: null,
    restarts: 0,
    restartTimer: null,
    disposed: false,
  };
  const stamp = () => (state.t0 ? Date.now() - state.t0 : 0);

  $("v-unsupported").hidden = Boolean(SR);
  $("v-mic").disabled = !SR;
  if (!SR) {
    $("v-status").className = "stage-status warn";
    $("v-status").textContent = "Speech recognition is not available in this browser — exports still work once segments exist.";
  }

  function setStatus(text, cls = "") {
    const s = $("v-status");
    s.textContent = text;
    s.className = `stage-status ${cls}`;
  }

  function paintProvider() {
    const p = providerId();
    const missing = p === "deepl" && !getKey();
    const chip = $("v-provider");
    chip.className = `chip ${missing ? "warn" : "info"}`;
    chip.textContent = `provider: ${p === "deepl" ? "DeepL" : "Demo"}${missing ? " · key locked" : ""}`;
    $("v-key-hint").hidden = !missing;
    $("v-key-hint").textContent = missing
      ? "DeepL is the default provider but no vault key is unlocked — segments will fail until you unlock it in Settings."
      : "";
  }

  async function fillTargets() {
    await fillLangSelect($("v-tgt"), {
      selected: localStorage.getItem("talkflow.tgt") || "DE",
      skip: $("v-speak").value,
      baseOnly: true,
    });
    localStorage.setItem("talkflow.tgt", $("v-tgt").value);
  }

  (async () => {
    await fillLangSelect($("v-speak"), {
      selected: localStorage.getItem("talkflow.speak") || "EN",
      baseOnly: true,
    });
    await fillTargets();
    paintProvider();
  })();

  $("v-speak").addEventListener("change", async () => {
    localStorage.setItem("talkflow.speak", $("v-speak").value);
    await fillTargets();
  });
  $("v-tgt").addEventListener("change", () => localStorage.setItem("talkflow.tgt", $("v-tgt").value));

  /* ---------------- microphone state machine ---------------- */
  $("v-mic").addEventListener("click", () => {
    if (state.phase === "listening") stopMic();
    else startMic();
  });

  function startMic() {
    if (!SR || state.phase === "listening") return;
    try {
      const r = new SR();
      r.continuous = true;
      r.interimResults = true;
      r.lang = bcp47($("v-speak").value);
      r.onresult = onResults;
      r.onerror = onError;
      r.onend = onEnd;
      state.rec = r;
      state.phase = "listening";
      state.restarts = 0;
      state.pendingStart = null;
      if (!state.t0) state.t0 = Date.now();
      r.start();
      $("v-mic").classList.add("active");
      $("v-mic").innerHTML = "&#9632; Stop";
      root.querySelector(".captions").hidden = false;
      setStatus("Listening… speak now.", "ok");
    } catch (e) {
      state.phase = "idle";
      setStatus(`Could not start recognition: ${e.message}`, "fail");
      toast(`Could not start recognition: ${e.message}`, "fail");
    }
  }

  function stopMic(message) {
    state.phase = "idle";
    clearTimeout(state.restartTimer);
    const rec = state.rec;
    state.rec = null;
    try { if (rec) rec.abort(); } catch { /* already stopped */ }
    $("v-mic").classList.remove("active");
    $("v-mic").innerHTML = "&#9679; Start listening";
    const done = state.segments.filter((s) => s.translated).length;
    setStatus(message || `Stopped — ${done} translated segment(s) captured.`, message ? "warn" : "");
  }

  function onEnd() {
    if (state.phase !== "listening" || state.disposed) return;
    state.restarts += 1;
    if (state.restarts > 120) {
      stopMic("Recognition kept stopping — press Start to resume.");
      return;
    }
    clearTimeout(state.restartTimer);
    state.restartTimer = setTimeout(() => {
      if (state.phase !== "listening" || !state.rec) return;
      try { state.rec.start(); } catch { /* onend will retry */ }
    }, 300);
  }

  function onError(ev) {
    const code = ev.error || "unknown";
    if (code === "aborted") return;
    if (code === "no-speech") {
      setStatus("No speech detected — still listening.", "warn");
      return;
    }
    if (code === "not-allowed" || code === "service-not-allowed" || code === "audio-capture") {
      toast(`Microphone unavailable (${code}).`, "fail");
      stopMic(`Microphone unavailable (${code}) — check browser permissions.`);
      return;
    }
    setStatus(`Recognition error: ${code}`, "fail");
    toast(`Recognition error: ${code}`, "fail");
  }

  function onResults(ev) {
    let interim = "";
    for (let i = ev.resultIndex; i < ev.results.length; i++) {
      const r = ev.results[i];
      const text = String(r[0]?.transcript || "").trim();
      if (r.isFinal) {
        interim = "";
        $("v-tentative").textContent = "";
        state.restarts = 0;
        if (text) {
          const start = state.pendingStart === null ? state.lastEnd : state.pendingStart;
          state.pendingStart = null;
          void capture(text, start);
        }
      } else {
        interim += String(r[0]?.transcript || "");
        if (state.pendingStart === null) state.pendingStart = stamp();
      }
    }
    if (interim) {
      $("v-tentative").textContent = interim;
      if (state.phase === "listening") setStatus("Listening… (interim)", "ok");
    }
  }

  /* ---------------- per-segment translation ---------------- */
  async function capture(source, startArg) {
    const tgtLang = $("v-tgt").value;
    const srcLang = $("v-speak").value;
    let start = Math.max(0, Number(startArg) || 0);
    let end = stamp();
    if (end <= start) end = start + 300;
    state.lastEnd = Math.max(state.lastEnd, end);
    const seg = { index: ++state.index, startMs: start, endMs: end, source, target: "", translated: false };
    state.segments.push(seg);

    $("v-concluded").textContent = source;
    $("v-target-line").textContent = "";
    const tr = document.createElement("tr");
    tr.innerHTML = `<td class="num">${seg.index}</td>
      <td class="num">${fmtClock(seg.startMs)} – ${fmtClock(seg.endMs)}</td>
      <td>${esc(source)}</td>
      <td class="cell-target"><span class="spin"></span></td>
      <td><button class="btn ghost sm" type="button" disabled>Speak</button></td>`;
    $("v-rows").appendChild(tr);
    $("v-empty").hidden = true;
    setStatus(`Translating segment ${seg.index}…`, "warn");

    const p = providerId();
    const key = p === "deepl" ? getKey() : null;
    if (p === "deepl" && !key) {
      failSegment(seg, tr, "DeepL key not unlocked — open Settings.");
      paintProvider();
      return;
    }

    try {
      const res = await apiPost("/api/translate", {
        text: source,
        source_lang: srcLang,
        target_lang: tgtLang,
        formality: "default",
        provider: p,
      }, { key, timeoutMs: 30000 });
      seg.target = String(res.text ?? "");
      seg.translated = Boolean(seg.target);
      if (state.disposed) return;
      tr.cells[3].innerHTML = esc(seg.target || "(empty translation)");
      const btn = tr.cells[4].querySelector("button");
      btn.disabled = !seg.target;
      btn.addEventListener("click", () => speak(seg.target, tgtLang));
      if (seg.index === state.index) $("v-target-line").textContent = seg.target;
      if (!seg.target) toast("The engine returned an empty translation.", "warn");
      if (state.phase === "listening") setStatus("Listening…", "ok");
    } catch (e) {
      if (!state.disposed) failSegment(seg, tr, humanError(e));
    }
  }

  function failSegment(seg, tr, message) {
    tr.cells[3].innerHTML = `<span class="chip fail">failed: ${esc(message)}</span>`;
    setStatus(`Segment ${seg.index} failed to translate.`, "fail");
    toast(message, "fail");
  }

  function speak(text, code) {
    if (!("speechSynthesis" in window)) {
      toast("Speech synthesis is not supported in this browser.", "fail");
      return;
    }
    try {
      const u = new SpeechSynthesisUtterance(text);
      u.lang = bcp47(code);
      u.rate = 1;
      speechSynthesis.cancel();
      speechSynthesis.speak(u);
    } catch (e) {
      toast(`Speech synthesis failed: ${e.message}`, "fail");
    }
  }

  /* ---------------- exports (local engine builder) ---------------- */
  for (const b of root.querySelectorAll(".xexport")) {
    b.addEventListener("click", () => {
      const withSource = $("v-incl-src").checked;
      const mapped = state.segments
        .filter((s) => s.translated && s.target)
        .map((s) => ({
          startMs: s.startMs,
          endMs: s.endMs,
          text: withSource ? `${s.source} / ${s.target}` : s.target,
        }));
      if (!mapped.length) { toast("No translated segments to export yet.", "warn"); return; }
      const fmt = b.dataset.fmt;
      try {
        const content = { srt: toSrt, vtt: toVtt, txt: toTxt, json: toJson }[fmt](mapped);
        download(content, `talkflow-captions.${fmt}`, fmt === "json" ? "application/json" : "text/plain;charset=utf-8");
        toast(`Exported ${mapped.length} subtitle block(s) as ${fmt.toUpperCase()}.`, "ok");
      } catch (e) {
        toast(`Export failed: ${e.message}`, "fail");
      }
    });
  }

  $("v-clear").addEventListener("click", () => {
    if (state.phase === "listening") stopMic("Stopped — transcript cleared.");
    state.segments = [];
    state.index = 0;
    state.t0 = 0;
    state.lastEnd = 0;
    state.pendingStart = null;
    $("v-rows").innerHTML = "";
    $("v-empty").hidden = false;
    $("v-concluded").textContent = "";
    $("v-target-line").textContent = "";
    $("v-tentative").textContent = "";
    root.querySelector(".captions").hidden = true;
    setStatus("Transcript cleared — press Start to listen again.");
  });

  window.addEventListener("focus", paintProvider);
  return () => {
    state.disposed = true;
    state.phase = "idle";
    clearTimeout(state.restartTimer);
    try { if (state.rec) state.rec.abort(); } catch { /* already stopped */ }
    try { if ("speechSynthesis" in window) speechSynthesis.cancel(); } catch { /* ignore */ }
    window.removeEventListener("focus", paintProvider);
  };
}
