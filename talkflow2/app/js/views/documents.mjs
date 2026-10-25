import { apiPost, esc, toast, download, fillLangSelect, humanError } from "../api.mjs";

const MAX_BYTES = 5 * 1024 * 1024;
const ALLOWED = new Set(["txt", "md", "html", "htm", "srt", "vtt", "json", "pdf"]);
const ACCEPT = ".txt,.md,.html,.srt,.vtt,.json,.pdf";

function extOf(name) {
  const m = String(name || "").match(/\.([A-Za-z0-9]+)$/);
  return m ? m[1].toLowerCase() : "";
}

function toBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  }
  return btoa(bin);
}

export function render(root) {
  root.innerHTML = `
  <div class="view">
    <h2 class="view-title">Document translation</h2>
    <div class="card">
      <div class="doc-bar">
        <span class="field-lbl">Target</span>
        <select id="d-tgt" aria-label="Target language"></select>
        <span class="spacer"></span>
        <button id="d-go" class="btn primary" type="button" disabled>Translate document</button>
      </div>
      <div id="d-drop" class="drop" role="button" tabindex="0" aria-label="Drop a document or browse">
        <strong>Drop a document here</strong> or choose a file
        <div><input id="d-file" type="file" accept="${ACCEPT}" aria-label="Choose a document"></div>
        <div class="drop-hint">txt · md · html · srt · vtt · json · pdf — up to 5 MB. Text is extracted and translated server-side.</div>
      </div>
      <div id="d-status" class="doc-status muted">No file selected.</div>
      <div id="d-progress" class="progress indeterminate" hidden><div class="bar"></div></div>
      <div id="d-meta" class="chips"></div>
      <div id="d-result" class="result doc-result empty" hidden></div>
      <div id="d-actions" class="chips"></div>
    </div>
  </div>`;

  const $ = (id) => root.querySelector("#" + id);
  let file = null;
  let busy = false;

  fillLangSelect($("d-tgt"), { selected: localStorage.getItem("talkflow.docTgt") || "DE", baseOnly: true });
  $("d-tgt").addEventListener("change", () => localStorage.setItem("talkflow.docTgt", $("d-tgt").value));

  function setStatus(text, kind = "") {
    const el = $("d-status");
    el.textContent = text;
    el.className = `doc-status ${kind}`.trim();
  }

  function validate(f) {
    if (!f) return "No file selected.";
    if (!f.size) return "That file is empty.";
    if (f.size > MAX_BYTES) return `File is ${(f.size / 1048576).toFixed(2)} MB — the limit is 5 MB.`;
    const ext = extOf(f.name);
    if (!ALLOWED.has(ext)) return `Unsupported file type “.${ext || "?"}” — accepted: ${ACCEPT}`;
    return null;
  }

  function setFile(f) {
    file = f || null;
    $("d-meta").innerHTML = "";
    $("d-actions").innerHTML = "";
    $("d-result").hidden = true;
    const err = file ? validate(file) : "No file selected.";
    if (err) {
      setStatus(file ? err : "No file selected.", file ? "error" : "muted");
      $("d-go").disabled = true;
      return;
    }
    setStatus(`${file.name} · ${(file.size / 1024).toFixed(1)} KB · ${extOf(file.name).toUpperCase()} — ready to translate.`, "ok");
    $("d-go").disabled = false;
  }

  $("d-file").addEventListener("change", () => setFile($("d-file").files?.[0] || null));

  const drop = $("d-drop");
  drop.addEventListener("click", (e) => {
    if (e.target !== $("d-file")) $("d-file").click();
  });
  drop.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("d-file").click(); }
  });
  drop.addEventListener("dragover", (e) => {
    e.preventDefault();
    drop.classList.add("drag");
  });
  drop.addEventListener("dragleave", () => drop.classList.remove("drag"));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    drop.classList.remove("drag");
    const f = e.dataTransfer?.files?.[0] || null;
    if (!f) return;
    try {
      const dt = new DataTransfer();
      dt.items.add(f);
      $("d-file").files = dt.files;
    } catch { /* file stays in memory even when the input cannot be synced */ }
    setFile(f);
  });

  function paint(res) {
    const meta = res.meta && typeof res.meta === "object" ? res.meta : {};
    const chips = [`<span class="chip info">kind: ${esc(res.kind || meta.kind || "?")}</span>`];
    if (meta.pages) chips.push(`<span class="chip">${esc(meta.pages)} page(s)</span>`);
    if (Array.isArray(res.segments)) chips.push(`<span class="chip">${res.segments.length} segment(s)</span>`);
    if (res.latency_ms != null) chips.push(`<span class="chip">${esc(res.latency_ms)} ms</span>`);
    const warnings = Array.isArray(meta.warnings) ? meta.warnings : [];
    for (const w of warnings) chips.push(`<span class="chip warn">${esc(w)}</span>`);
    if (!warnings.length) chips.push(`<span class="chip ok">no extraction warnings</span>`);
    $("d-meta").innerHTML = chips.join("");

    const out = $("d-result");
    out.hidden = false;
    out.className = "result doc-result";
    out.textContent = res.text ?? "(the server returned empty text)";

    const filename = res.filename || "translated.txt";
    $("d-actions").innerHTML = `<button id="d-dl" class="btn primary sm" type="button">Download ${esc(filename)}</button>`;
    $("d-dl").addEventListener("click", () => {
      download(res.text || "", filename, "text/plain;charset=utf-8");
      toast("Download started.", "ok");
    });
    setStatus(`Translated ${filename} in ${res.latency_ms ?? "?"} ms.`, "ok");
  }

  $("d-go").addEventListener("click", async () => {
    if (busy) return;
    if (!$("d-tgt").value) { setStatus("Choose a target language first.", "error"); return; }
    const err = validate(file);
    if (err) { setStatus(err, "error"); toast(err, "fail"); return; }
    busy = true;
    $("d-go").disabled = true;
    $("d-go").textContent = "Translating…";
    $("d-meta").innerHTML = "";
    $("d-actions").innerHTML = "";
    $("d-result").hidden = true;
    $("d-progress").hidden = false;
    $("d-progress").className = "progress indeterminate";
    setStatus(`Decoding ${file.name} and translating to ${$("d-tgt").value}…`);
    try {
      const buf = await file.arrayBuffer();
      const res = await apiPost("/api/document", {
        filename: file.name,
        content_base64: toBase64(buf),
        target_lang: $("d-tgt").value,
      }, { timeoutMs: 120000 });
      paint(res);
    } catch (e) {
      const msg = humanError(e);
      setStatus(`Document translation failed: ${msg}`, "error");
      toast(`Document translation failed: ${msg}`, "fail");
    } finally {
      busy = false;
      $("d-progress").hidden = true;
      $("d-progress").className = "progress";
      $("d-go").textContent = "Translate document";
      $("d-go").disabled = !file || Boolean(validate(file));
    }
  });

  return () => {};
}
