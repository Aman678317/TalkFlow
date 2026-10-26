import { apiGet, apiPost, apiDelete, esc, humanError } from "../api.mjs";
import { getKey, hasVault } from "../vault.mjs";

function b64(text) {
  return btoa(String(text));
}

const CHECKS = [
  {
    id: "health",
    name: "API health",
    run: async () => {
      const h = await apiGet("/api/health", { timeoutMs: 8000 });
      if (!h || h.status !== "ok") throw new Error(`Health status was “${h?.status ?? "missing"}”`);
      return { detail: `v${h.version ?? "?"} · ${h.agents ?? 0} agents · uptime ${Math.round((h.uptime_ms || 0) / 1000)} s` };
    },
  },
  {
    id: "detect",
    name: "Language detection",
    run: async () => {
      const d = await apiPost("/api/detect", { text: "Hello world, how are you today?" });
      if (typeof d.lang !== "string" || !d.lang) throw new Error("No language code returned");
      if (!(Number(d.confidence) >= 0 && Number(d.confidence) <= 1)) throw new Error("Confidence was not in 0..1");
      return { detail: `${String(d.lang).toUpperCase()} · ${Math.round(Number(d.confidence) * 100)}% · ${d.status || "success"}` };
    },
  },
  {
    id: "translate",
    name: "Local translate EN → DE",
    run: async () => {
      const r = await apiPost("/api/translate", {
        text: "Hello, how are you?",
        source_lang: "EN",
        target_lang: "DE",
        provider: "local",
      }, { timeoutMs: 30000 });
      if (typeof r.text !== "string" || !r.text.trim()) throw new Error("Translation came back empty");
      return {
        detail: `“${r.text.slice(0, 90)}” · coverage ${Math.round((Number(r.coverage) || 0) * 100)}% · trace ${(r.agent_trace || []).length}`,
      };
    },
  },
  {
    id: "write",
    name: "Write correction + diff",
    run: async () => {
      const text = "teh quick brown fox has alot of mistakes.";
      const r = await apiPost("/api/write", { text, mode: "correct", style: "default", provider: "local" });
      if (typeof r.corrected !== "string" || !r.corrected.trim()) throw new Error("Corrected text came back empty");
      const diffs = Array.isArray(r.diff) ? r.diff.length : 0;
      const changes = Array.isArray(r.changes) ? r.changes.length : 0;
      if (!diffs && !changes && r.corrected.trim() === text) throw new Error("No corrections were produced");
      return { detail: `${changes} change(s) · ${diffs} diff segment(s) · “${r.corrected.slice(0, 70)}”` };
    },
  },
  {
    id: "glossary",
    name: "Glossary CRUD roundtrip",
    run: async () => {
      const name = `Self-check ${Date.now()}`;
      let id = null;
      let deleted = false;
      try {
        const created = await apiPost("/api/glossary", { name });
        id = created.id;
        if (!id) throw new Error("Create returned no id");
        await apiPost(`/api/glossary/${encodeURIComponent(id)}/entries`, {
          source_term: "selfcheck-source",
          target_term: "selfcheck-target",
          source_lang: "EN",
          target_lang: "DE",
        });
        const store = await apiGet(`/api/glossary/${encodeURIComponent(id)}`);
        const found = (Array.isArray(store.entries) ? store.entries : [])
          .some((e) => String(e.source_term ?? e.sourceTerm) === "selfcheck-source");
        if (!found) throw new Error("Entry missing after add");
        await apiDelete(`/api/glossary/${encodeURIComponent(id)}`);
        deleted = true;
        let gone = false;
        try { await apiGet(`/api/glossary/${encodeURIComponent(id)}`); }
        catch (e) { gone = e.status === 404; }
        if (!gone) throw new Error("Store still returns after delete");
        return { detail: `store ${id} created → entry added → deleted (404 verified)` };
      } finally {
        if (id && !deleted) {
          try { await apiDelete(`/api/glossary/${encodeURIComponent(id)}`); } catch { /* best-effort cleanup */ }
        }
      }
    },
  },
  {
    id: "document",
    name: "Document inline TXT",
    run: async () => {
      const source = "Hello there. Thank you very much. See you tomorrow.";
      const r = await apiPost("/api/document", {
        filename: "selfcheck.txt",
        content_base64: b64(source),
        target_lang: "DE",
      }, { timeoutMs: 120000 });
      if (typeof r.text !== "string" || !r.text.trim()) throw new Error("Document output was empty");
      if (r.kind !== "txt") throw new Error(`Expected kind txt, got “${r.kind}”`);
      return { detail: `${(r.segments || []).length} segment(s) · ${r.filename || "selfcheck-translated.txt"}` };
    },
  },
  {
    id: "deepl",
    name: "DeepL key validate (optional)",
    run: async () => {
      const key = getKey();
      if (!key) {
        return {
          status: "skip",
          detail: hasVault() ? "Vault is locked — unlock it in Settings to run this check." : "No DeepL key saved — optional check skipped.",
        };
      }
      let r;
      try {
        r = await apiPost("/api/deepl/validate", {}, { key, timeoutMs: 25000 });
      } catch (e) {
        if (e.data?.valid === false) throw new Error(`Key rejected (${e.data.reason || "format"})`);
        throw e;
      }
      if (!r.valid) throw new Error("Server reported the key as invalid");
      const quota = r.character_count == null || !Number.isFinite(Number(r.character_count))
        ? ""
        : ` · ${r.character_count}/${r.character_limit ?? "?"} chars`;
      const detail = `${r.tier || "?"} · ${r.host || "?"}${quota}${r.live_check ? ` · live check ${r.live_check}` : ""}`;
      if (r.live_check === "failed") return { status: "skip", detail: `${detail} (format valid, live check failed)` };
      return { detail };
    },
  },
];

export function render(root) {
  root.innerHTML = `
  <div class="view">
    <div class="row tests-toolbar">
      <h2 class="view-title">Tests — self-checks</h2>
      <span class="spacer"></span>
      <span id="t-summary" class="tests-overall muted">Not run yet</span>
      <button id="t-run" class="btn primary" type="button">Run all checks</button>
    </div>
    <div class="banner warn">These checks send real requests to this server and show exactly what happened. The optional DeepL check only runs when an unlocked vault key exists.</div>
    <div class="card">
      <div class="table-scroll">
        <table class="table">
          <thead><tr><th>Check</th><th>Status</th><th>ms</th><th>Detail</th></tr></thead>
          <tbody id="t-rows"></tbody>
        </table>
      </div>
    </div>
  </div>`;

  const $ = (id) => root.querySelector("#" + id);
  $("t-rows").innerHTML = CHECKS.map((c) => `
    <tr data-check="${esc(c.id)}">
      <td>${esc(c.name)}</td>
      <td class="t-status-cell"><span class="pill pending t-status">pending</span></td>
      <td class="num t-ms">—</td>
      <td class="muted t-detail"></td>
    </tr>`).join("");

  let running = false;
  let disposed = false;

  function setRow(id, status, ms, detail) {
    const row = root.querySelector(`tr[data-check="${id}"]`);
    if (!row) return;
    const pill = row.querySelector(".t-status");
    pill.className = `pill t-status ${status === "pass" ? "ok" : status === "fail" ? "fail" : status === "skip" ? "skip" : "pending"}`;
    pill.innerHTML = status === "running" ? `<span class="spin"></span> running` : esc(status);
    row.querySelector(".t-ms").textContent = ms == null ? "—" : `${ms} ms`;
    row.querySelector(".t-detail").textContent = detail || "";
  }

  async function runAll() {
    if (running) return;
    running = true;
    const btn = $("t-run");
    btn.disabled = true;
    btn.textContent = "Running…";
    let pass = 0, fail = 0, skip = 0, total = 0;
    for (const check of CHECKS) {
      if (disposed) return;
      setRow(check.id, "running", null, "");
      const started = performance.now();
      let status = "fail";
      let detail = "";
      try {
        const out = await check.run();
        status = out?.status === "skip" ? "skip" : "pass";
        detail = out?.detail || "";
      } catch (e) {
        status = "fail";
        detail = humanError(e);
      }
      const ms = Math.round(performance.now() - started);
      total += ms;
      if (disposed) return;
      if (status === "pass") pass += 1;
      else if (status === "skip") skip += 1;
      else fail += 1;
      setRow(check.id, status, ms, detail);
    }
    $("t-summary").textContent = `${pass} passed · ${fail} failed · ${skip} skipped · ${total} ms total`;
    $("t-summary").className = `tests-overall ${fail ? "error-text" : "muted"}`;
    btn.disabled = false;
    btn.textContent = "Run all checks";
    running = false;
  }

  $("t-run").addEventListener("click", runAll);
  return () => { disposed = true; };
}
