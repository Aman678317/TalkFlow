import { apiGet, apiPost, fillLangSelect, esc, toast, humanError } from "../api.mjs";
import { getKey } from "../vault.mjs";

const PROV_KEY = "talkflow.provider";
const SRC_KEY = "talkflow.src";
const TGT_KEY = "talkflow.tgt";

const normProvider = (v) => (v === "deepl" ? "deepl" : "local");

export function render(root) {
  root.innerHTML = `
  <div class="view">
    <h2 class="view-title">Translate</h2>
    <div class="card">
      <div class="translate-grid">
        <section class="pane">
          <div class="pane-bar">
            <span class="lbl">Source</span>
            <select id="src-lang" aria-label="Source language"></select>
            <span class="clamp"></span>
          </div>
          <textarea id="src" placeholder="Type or paste text to translate…" spellcheck="false" aria-label="Source text"></textarea>
          <div class="pane-foot">
            <button id="detect-badge" class="detect-badge" type="button" hidden></button>
            <span class="spacer"></span>
            <span id="count" class="muted">0 chars</span>
          </div>
          <div id="detect-warn" class="warn-text" hidden></div>
        </section>
        <section class="pane">
          <div class="pane-bar">
            <span class="lbl">Target</span>
            <select id="tgt-lang" aria-label="Target language"></select>
            <select id="formality" title="Formality" aria-label="Formality">
              <option value="default">Formality: default</option>
              <option value="informal">Formality: informal</option>
              <option value="formal">Formality: formal</option>
            </select>
          </div>
          <div id="result" class="result empty">Translation appears here</div>
          <div class="result-foot">
            <div id="coverage" class="progress" hidden><div id="coverage-bar" class="bar"></div></div>
            <span id="coverage-note"></span>
            <span class="spacer"></span>
            <button id="copy" class="btn ghost sm" type="button" hidden>Copy</button>
          </div>
          <div id="chips" class="chips"></div>
          <details id="trace" class="trace" hidden>
            <summary id="trace-summary">Agent trace</summary>
            <div class="table-scroll"><table class="table trace-table">
              <thead><tr><th>Agent</th><th>Decision</th><th>ms</th></tr></thead>
              <tbody id="trace-rows"></tbody>
            </table></div>
          </details>
        </section>
      </div>
      <div class="translate-actions">
        <div class="seg" id="provider-seg" role="group" aria-label="Translation provider">
          <button type="button" data-provider="local" class="on">Demo</button>
          <button type="button" data-provider="deepl">DeepL</button>
        </div>
        <button id="ctx-toggle" class="btn ghost sm" type="button" aria-expanded="false">Context ▸</button>
        <select id="glossary" title="Protect terms with a glossary" aria-label="Glossary">
          <option value="">No glossary</option>
        </select>
        <span class="spacer"></span>
        <span class="kbd-hint"><code>Ctrl</code>+<code>Enter</code></span>
        <button id="go" class="btn primary" type="button">Translate</button>
      </div>
      <div id="prov-hint" class="warn-text" hidden></div>
      <div id="ctx-panel" class="context-panel" hidden>
        <input id="ctx" type="text" placeholder="Optional context, e.g. “river shore” — used for homograph disambiguation">
      </div>
    </div>
  </div>`;

  const $ = (id) => root.querySelector("#" + id);
  const srcSel = $("src-lang"), tgtSel = $("tgt-lang"), srcText = $("src");
  const state = {
    provider: normProvider(localStorage.getItem(PROV_KEY)),
    detect: null,
    seq: 0,
    timer: null,
    lastText: "",
  };

  /* ---------------- provider ---------------- */
  function paintProvider() {
    for (const b of $("provider-seg").querySelectorAll("button")) {
      b.classList.toggle("on", b.dataset.provider === state.provider);
      b.setAttribute("aria-pressed", String(b.dataset.provider === state.provider));
    }
    const missing = state.provider === "deepl" && !getKey();
    $("prov-hint").hidden = !missing;
    $("prov-hint").textContent = missing
      ? "DeepL is selected but no vault key is unlocked for this tab. Open Settings → API key vault, or switch to Demo."
      : "";
  }

  $("provider-seg").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    state.provider = normProvider(b.dataset.provider);
    localStorage.setItem(PROV_KEY, state.provider);
    paintProvider();
  });

  /* ---------------- context panel ---------------- */
  $("ctx-toggle").addEventListener("click", () => {
    const panel = $("ctx-panel");
    panel.hidden = !panel.hidden;
    $("ctx-toggle").setAttribute("aria-expanded", String(!panel.hidden));
    $("ctx-toggle").textContent = panel.hidden ? "Context ▸" : "Context ▾";
    if (!panel.hidden) $("ctx").focus();
  });

  /* ---------------- glossary ---------------- */
  async function loadGlossary() {
    const sel = $("glossary");
    try {
      const d = await apiGet("/api/glossary");
      const stores = Array.isArray(d) ? d : d.glossaries || d.stores || [];
      sel.innerHTML = `<option value="">No glossary</option>` + stores
        .map((s) => `<option value="${esc(s.id)}">${esc(s.name)} (${(s.entries || []).length})</option>`)
        .join("");
    } catch (e) {
      sel.innerHTML = `<option value="">No glossary</option><option value="__unavailable" disabled>Glossaries unavailable</option>`;
      $("detect-warn").hidden = false;
      $("detect-warn").textContent = `Glossary list could not load: ${humanError(e)}`;
    }
  }

  /* ---------------- detection ---------------- */
  function paintDetect() {
    const badge = $("detect-badge"), warn = $("detect-warn");
    const d = state.detect;
    if (!d) { badge.hidden = true; warn.hidden = true; return; }
    const lang = String(d.lang || "").toUpperCase();
    const conf = Math.round((Number(d.confidence) || 0) * 100);
    const auto = srcSel.value === "AUTO";
    const uncertain = auto && (!lang || d.status !== "success" || conf < 55);
    badge.hidden = false;
    badge.className = `detect-badge${auto ? "" : " pinned"}${uncertain ? " warn" : ""}`;
    badge.textContent = auto
      ? `Detected ${lang || "?"} · ${conf}%${uncertain ? " · low confidence" : ""}`
      : `Source ${srcSel.value} · detected ${lang || "?"} ${conf}%`;
    badge.title = auto ? "Click to pin the detected language as the source" : "Click to return to auto-detect";
    warn.hidden = !uncertain;
    if (uncertain) {
      warn.textContent = !lang || d.status === "no_language_detected"
        ? "No language detected — choose the source language manually."
        : `Auto-detect is uncertain (${conf}%). Confirm the source language (click the badge to pin it).`;
    }
  }

  async function requestDetect() {
    const text = srcText.value.trim();
    if (!text) {
      state.detect = null;
      state.seq++;
      paintDetect();
      return;
    }
    const seq = ++state.seq;
    try {
      const d = await apiPost("/api/detect", { text });
      if (seq !== state.seq) return;
      state.detect = d;
      paintDetect();
    } catch (e) {
      if (seq !== state.seq) return;
      state.detect = null;
      const badge = $("detect-badge"), warn = $("detect-warn");
      badge.hidden = false;
      badge.className = "detect-badge warn";
      badge.textContent = "Detection unavailable";
      warn.hidden = false;
      warn.textContent = humanError(e);
    }
  }

  $("detect-badge").addEventListener("click", async () => {
    if (srcSel.value !== "AUTO") {
      srcSel.value = "AUTO";
      localStorage.setItem(SRC_KEY, "AUTO");
      await rebuildTargets();
      paintDetect();
      return;
    }
    const lang = String(state.detect?.lang || "").toUpperCase();
    if (!lang || ![...srcSel.options].some((o) => o.value === lang)) return;
    srcSel.value = lang;
    localStorage.setItem(SRC_KEY, lang);
    await rebuildTargets();
    paintDetect();
  });

  srcText.addEventListener("input", () => {
    $("count").textContent = `${srcText.value.length} chars`;
    clearTimeout(state.timer);
    state.timer = setTimeout(requestDetect, 450);
  });

  /* ---------------- language selects ---------------- */
  async function rebuildTargets() {
    const prev = tgtSel.value || localStorage.getItem(TGT_KEY) || "DE";
    await fillLangSelect(tgtSel, {
      selected: prev,
      skip: srcSel.value === "AUTO" ? null : srcSel.value,
      baseOnly: true,
    });
    localStorage.setItem(TGT_KEY, tgtSel.value);
  }

  srcSel.addEventListener("change", async () => {
    localStorage.setItem(SRC_KEY, srcSel.value);
    await rebuildTargets();
    paintDetect();
    if (srcSel.value === "AUTO" && srcText.value.trim()) void requestDetect();
  });

  tgtSel.addEventListener("change", () => {
    localStorage.setItem(TGT_KEY, tgtSel.value);
    $("result").dataset.target = tgtSel.value;
  });

  (async () => {
    await fillLangSelect(srcSel, {
      auto: true,
      selected: localStorage.getItem(SRC_KEY) || "AUTO",
      baseOnly: true,
    });
    await rebuildTargets();
    paintProvider();
    paintDetect();
    void loadGlossary();
  })();

  /* ---------------- result painting ---------------- */
  function clearOutput(kind, message) {
    const result = $("result");
    result.className = `result ${kind}`;
    result.textContent = message;
    $("chips").innerHTML = "";
    $("coverage").hidden = true;
    $("coverage-note").textContent = "";
    $("trace").hidden = true;
    $("copy").hidden = true;
    state.lastText = "";
  }

  function paintResult(res, roundTripMs) {
    const result = $("result");
    result.className = "result";
    result.textContent = String(res.text ?? "");
    state.lastText = String(res.text ?? "");

    const notes = Array.isArray(res.notes) ? res.notes : res.notes ? [String(res.notes)] : [];
    const chips = [`<span class="chip info">${esc(res.provider === "deepl" ? "DeepL live" : "Demo engine")}</span>`];
    if (res.detected_source_language) {
      chips.push(`<span class="chip">detected ${esc(String(res.detected_source_language).toUpperCase())}</span>`);
    }
    if (res.latency_ms != null) chips.push(`<span class="chip">server ${esc(res.latency_ms)} ms</span>`);
    if (roundTripMs != null) chips.push(`<span class="chip">round-trip ${esc(roundTripMs)} ms</span>`);
    if (res.chars_billed != null) chips.push(`<span class="chip">${esc(res.chars_billed)} chars billed</span>`);
    for (const n of notes) chips.push(`<span class="chip warn">${esc(n)}</span>`);
    $("chips").innerHTML = chips.join("");

    const cov = typeof res.coverage === "number" ? Math.max(0, Math.min(1, res.coverage)) : null;
    $("coverage").hidden = cov === null;
    if (cov !== null) {
      const bar = $("coverage-bar");
      bar.style.width = `${Math.round(cov * 100)}%`;
      bar.className = `bar${cov < 0.6 ? " low" : ""}`;
      $("coverage-note").textContent = `Coverage ${Math.round(cov * 100)}%`;
    } else {
      $("coverage-note").textContent = "";
    }

    const trace = Array.isArray(res.agent_trace) ? res.agent_trace : [];
    $("trace").hidden = trace.length === 0;
    $("trace-summary").textContent = `Agent trace (${trace.length})`;
    $("trace-rows").innerHTML = trace.map((t) =>
      `<tr><td><span class="chip info">${esc(t.agent ?? "agent")}</span></td><td>${esc(t.decision ?? "—")}</td><td class="num">${t.ms != null ? `${esc(t.ms)} ms` : "—"}</td></tr>`).join("");

    $("copy").hidden = !state.lastText;
  }

  /* ---------------- translate ---------------- */
  async function translate() {
    const text = srcText.value.trim();
    if (!text) { toast("Enter some text to translate.", "warn"); srcText.focus(); return; }
    if (!tgtSel.value) { toast("Choose a target language.", "warn"); return; }

    const key = state.provider === "deepl" ? getKey() : null;
    if (state.provider === "deepl" && !key) {
      clearOutput("error", "DeepL is selected but no key is unlocked for this tab. Open Settings → API key vault, or switch to Demo.");
      toast("Unlock your DeepL key in Settings first.", "fail");
      return;
    }

    const go = $("go");
    go.disabled = true;
    go.textContent = "Translating…";
    clearOutput("loading", "Translating…");
    const started = performance.now();
    try {
      const res = await apiPost("/api/translate", {
        text,
        source_lang: srcSel.value === "AUTO" ? "auto" : srcSel.value,
        target_lang: tgtSel.value,
        formality: $("formality").value,
        context: $("ctx").value.trim(),
        glossary_id: state.provider === "local" ? ($("glossary").value || null) : null,
        provider: state.provider,
      }, { key, timeoutMs: 30000 });
      paintResult(res, Math.round(performance.now() - started));
      if (state.provider === "local" && typeof res.coverage === "number" && res.coverage < 0.6) {
        toast("Low coverage — the demo lexicon only partially covers this text.", "warn");
      }
    } catch (e) {
      clearOutput("error", `Translation failed: ${humanError(e)}`);
      toast(humanError(e), "fail");
    } finally {
      go.disabled = false;
      go.textContent = "Translate";
    }
  }

  $("go").addEventListener("click", translate);
  srcText.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); void translate(); }
  });

  $("copy").addEventListener("click", async () => {
    if (!state.lastText) return;
    try {
      await navigator.clipboard.writeText(state.lastText);
      toast("Translation copied.", "ok");
    } catch {
      toast("Clipboard is unavailable in this browser.", "fail");
    }
  });

  window.addEventListener("focus", paintProvider);
  return () => {
    clearTimeout(state.timer);
    state.seq++;
    window.removeEventListener("focus", paintProvider);
  };
}
