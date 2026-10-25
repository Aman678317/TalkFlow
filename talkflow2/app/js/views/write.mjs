import { apiPost, esc, toast, humanError } from "../api.mjs";
import { getKey } from "../vault.mjs";

const PROV_KEY = "talkflow.provider";
const normProvider = (v) => (v === "deepl" ? "deepl" : "local");

/** Token-level LCS diff so DeepL Write (which returns no diff) still renders del/ins honestly. */
function diffWords(before, after) {
  const a = String(before).match(/\s+|\S+/g) || [];
  const b = String(after).match(/\s+|\S+/g) || [];
  if (a.join("") === b.join("")) return [{ kind: "eq", value: String(after) }];
  if (a.length * b.length > 810000) {
    return [{ kind: "del", value: String(before) }, { kind: "ins", value: String(after) }];
  }
  const n = a.length, m = b.length;
  const dp = [];
  for (let i = 0; i <= n; i++) dp.push(new Uint32Array(m + 1));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const out = [];
  const push = (kind, value) => {
    const last = out[out.length - 1];
    if (last && last.kind === kind) last.value += value;
    else out.push({ kind, value });
  };
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) { push("eq", a[i]); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { push("del", a[i]); i++; }
    else { push("ins", b[j]); j++; }
  }
  while (i < n) push("del", a[i++]);
  while (j < m) push("ins", b[j++]);
  return out;
}

export function render(root) {
  root.innerHTML = `
  <div class="view">
    <h2 class="view-title">Write — correct &amp; rephrase English</h2>
    <div class="card write-card">
      <textarea id="w-src" placeholder="Type English text to correct or rephrase — e.g. “teh quick brown fox”…" spellcheck="false" aria-label="English text"></textarea>
      <div class="write-actions">
        <div class="seg" id="w-mode" role="group" aria-label="Writing mode">
          <button type="button" data-mode="correct" class="on">Correct</button>
          <button type="button" data-mode="rephrase">Rephrase</button>
        </div>
        <select id="w-style" title="Writing style (rephrase mode)" aria-label="Writing style">
          <option value="default">Style: default</option>
          <option value="business">Style: business</option>
          <option value="academic">Style: academic</option>
          <option value="casual">Style: casual</option>
          <option value="simple">Style: simple</option>
        </select>
        <span id="w-prov" class="chip">Demo engine</span>
        <span class="spacer"></span>
        <span class="kbd-hint"><code>Ctrl</code>+<code>Enter</code></span>
        <button id="w-go" class="btn primary" type="button">Write</button>
      </div>
      <div id="w-hint" class="warn-text" hidden></div>
      <div id="w-out" class="result diff empty">Corrected text and a word-diff appear here.</div>
      <div id="w-meta" class="chips"></div>
      <div class="table-scroll">
        <table id="w-table" class="table changes" hidden>
          <thead><tr><th>Change</th><th>Before</th><th>After</th><th>Why</th></tr></thead>
          <tbody id="w-rows"></tbody>
        </table>
      </div>
    </div>
  </div>`;

  const $ = (id) => root.querySelector("#" + id);
  const provider = normProvider(localStorage.getItem(PROV_KEY));
  let mode = "correct";

  $("w-prov").className = `chip ${provider === "deepl" ? "info" : ""}`;
  $("w-prov").textContent = provider === "deepl" ? "DeepL live" : "Demo engine";
  if (provider === "deepl" && !getKey()) {
    $("w-hint").hidden = false;
    $("w-hint").textContent = "DeepL is the default provider but no vault key is unlocked. Open Settings to unlock it, or switch the default to Demo.";
  }

  const seg = $("w-mode");
  seg.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    mode = b.dataset.mode;
    for (const x of seg.querySelectorAll("button")) {
      x.classList.toggle("on", x === b);
      x.setAttribute("aria-pressed", String(x === b));
    }
  });

  function paint(res) {
    const out = $("w-out");
    const corrected = String(res.corrected ?? "");
    const before = String(res.original ?? $("w-src").value);
    const serverDiff = Array.isArray(res.diff) ? res.diff : [];
    const diff = serverDiff.length ? serverDiff : diffWords(before, corrected);
    out.className = "result diff";
    out.innerHTML = diff.map((seg) => {
      const kind = seg.kind === "del" ? "del" : seg.kind === "ins" ? "ins" : "eq";
      return kind === "eq" ? esc(seg.value) : `<span class="${kind}">${esc(seg.value)}</span>`;
    }).join("");

    const changes = Array.isArray(res.changes) ? res.changes : [];
    const chips = [
      `<span class="chip info">${esc(res.provider === "deepl" ? "DeepL live" : "Demo engine")}</span>`,
      res.latency_ms != null ? `<span class="chip">${esc(res.latency_ms)} ms</span>` : "",
      `<span class="chip">${changes.length} change(s)</span>`,
      `<button id="w-copy" class="btn ghost sm" type="button">Copy result</button>`,
    ].filter(Boolean);
    if (!changes.length && corrected.trim() === before.trim()) chips.push(`<span class="chip ok">No changes suggested</span>`);
    $("w-meta").innerHTML = chips.join("");
    $("w-copy").addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(corrected);
        toast("Result copied to clipboard.", "ok");
      } catch {
        toast("Clipboard is unavailable in this browser.", "fail");
      }
    });

    $("w-table").hidden = changes.length === 0;
    $("w-rows").innerHTML = changes.map((c) =>
      `<tr><td><span class="chip info">${esc(c.type ?? "change")}</span></td>
        <td><span class="del">${esc(c.before ?? "")}</span></td>
        <td><span class="ins">${esc(c.after ?? "")}</span></td>
        <td class="muted">${esc(c.description || "—")}</td></tr>`).join("");
  }

  async function run() {
    const text = $("w-src").value.trim();
    if (!text) { toast("Enter some English text first.", "warn"); $("w-src").focus(); return; }
    const key = provider === "deepl" ? getKey() : null;
    if (provider === "deepl" && !key) {
      $("w-out").className = "result diff error";
      $("w-out").textContent = "DeepL is the default provider but no key is unlocked. Open Settings → API key vault, or switch the default to Demo.";
      toast("Unlock your DeepL key in Settings first.", "fail");
      return;
    }

    const btn = $("w-go"), out = $("w-out");
    btn.disabled = true;
    btn.textContent = "Writing…";
    out.className = "result diff loading";
    out.textContent = "Writing…";
    $("w-table").hidden = true;
    $("w-rows").innerHTML = "";
    $("w-meta").innerHTML = "";
    try {
      const res = await apiPost("/api/write", {
        text,
        mode,
        style: $("w-style").value,
        provider,
      }, { key, timeoutMs: 30000 });
      paint(res);
    } catch (e) {
      out.className = "result diff error";
      out.textContent = `Write failed: ${humanError(e)}`;
      toast(humanError(e), "fail");
    } finally {
      btn.disabled = false;
      btn.textContent = "Write";
    }
  }

  $("w-go").addEventListener("click", run);
  $("w-src").addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); void run(); }
  });

  return () => {};
}
