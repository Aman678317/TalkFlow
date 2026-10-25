import { apiGet, apiPost, apiDelete, fillLangSelect, esc, toast, humanError } from "../api.mjs";

const normEntry = (e) => ({
  source_term: String(e?.source_term ?? e?.sourceTerm ?? ""),
  target_term: String(e?.target_term ?? e?.targetTerm ?? ""),
  source_lang: String(e?.source_lang ?? e?.sourceLang ?? "EN"),
  target_lang: String(e?.target_lang ?? e?.targetLang ?? "DE"),
});

export function render(root) {
  root.innerHTML = `
  <div class="view">
    <div class="row">
      <h2 class="view-title">Glossary</h2>
      <span class="spacer"></span>
      <button id="g-refresh" class="btn ghost sm" type="button">Refresh</button>
    </div>
    <div id="g-error" class="banner fail" hidden></div>
    <div class="card grid-side">
      <section class="store-pane">
        <h3>Stores</h3>
        <div class="row-form">
          <input id="g-name" type="text" placeholder="New glossary name" aria-label="New glossary name">
          <button id="g-create" class="btn primary sm" type="button">Create</button>
        </div>
        <div id="g-list" class="store-list"></div>
        <div id="g-empty" class="empty">No glossaries yet — create one to protect brand and domain terms.</div>
      </section>
      <section class="detail-pane">
        <div id="g-detail-empty" class="empty">Select or create a glossary to manage its entries.</div>
        <div id="g-detail" hidden>
          <div class="row">
            <h3 id="g-title" style="margin:0"></h3>
            <span id="g-count" class="chip"></span>
            <span class="spacer"></span>
            <button id="g-del" class="btn danger sm" type="button">Delete store</button>
          </div>
          <div class="table-scroll" style="margin-top:12px">
            <table class="table">
              <thead><tr><th>Source term</th><th>Lang</th><th>Target term</th><th>Lang</th></tr></thead>
              <tbody id="g-rows"></tbody>
            </table>
          </div>
          <div id="g-rows-empty" class="empty">No entries in this glossary yet.</div>
          <h3 style="margin-top:16px">Add entry</h3>
          <div class="row-form">
            <input id="g-src" type="text" placeholder="Source term" aria-label="Source term">
            <select id="g-slang" aria-label="Source language"></select>
            <span class="muted">→</span>
            <input id="g-tgt" type="text" placeholder="Target term" aria-label="Target term">
            <select id="g-tlang" aria-label="Target language"></select>
            <button id="g-add" class="btn primary sm" type="button">Add</button>
          </div>
        </div>
      </section>
    </div>
  </div>`;

  const $ = (id) => root.querySelector("#" + id);
  const state = { stores: [], selectedId: null };

  const current = () => state.stores.find((s) => s.id === state.selectedId) || null;

  function showError(message) {
    $("g-error").hidden = !message;
    $("g-error").textContent = message || "";
  }

  function renderList() {
    $("g-list").innerHTML = state.stores.map((s) => `
      <button class="store-item${s.id === state.selectedId ? " selected" : ""}" data-id="${esc(s.id)}" type="button">
        <span><strong>${esc(s.name || "(unnamed)")}</strong><br><span class="muted">${s.entries.length} entr${s.entries.length === 1 ? "y" : "ies"}</span></span>
        <span class="muted">›</span>
      </button>`).join("");
    $("g-empty").hidden = state.stores.length > 0;
    for (const b of $("g-list").querySelectorAll(".store-item")) {
      b.addEventListener("click", () => {
        state.selectedId = b.dataset.id;
        renderList();
        renderDetail();
      });
    }
  }

  function renderDetail() {
    const st = current();
    $("g-detail").hidden = !st;
    $("g-detail-empty").hidden = Boolean(st);
    if (!st) return;
    $("g-title").textContent = st.name || "(unnamed)";
    $("g-count").textContent = `${st.entries.length} entr${st.entries.length === 1 ? "y" : "ies"}`;
    $("g-rows").innerHTML = st.entries.map((e) => `
      <tr>
        <td>${esc(e.source_term)}</td>
        <td><span class="chip">${esc(e.source_lang)}</span></td>
        <td>${esc(e.target_term)}</td>
        <td><span class="chip">${esc(e.target_lang)}</span></td>
      </tr>`).join("");
    $("g-rows-empty").hidden = st.entries.length > 0;
  }

  function renderAll() {
    renderList();
    renderDetail();
  }

  async function load(preferId = null) {
    try {
      const d = await apiGet("/api/glossary");
      const raw = Array.isArray(d) ? d : d.glossaries || d.stores || [];
      state.stores = raw.map((s) => ({
        id: String(s.id),
        name: String(s.name || ""),
        entries: (Array.isArray(s.entries) ? s.entries : []).map(normEntry),
      }));
      if (preferId && state.stores.some((s) => s.id === String(preferId))) state.selectedId = String(preferId);
      if (!state.stores.some((s) => s.id === state.selectedId)) state.selectedId = state.stores[0]?.id ?? null;
      showError("");
      renderAll();
    } catch (e) {
      showError(`Could not load glossaries: ${humanError(e)}`);
    }
  }

  async function createStore() {
    const name = $("g-name").value.trim();
    if (!name) { toast("Enter a glossary name first.", "warn"); $("g-name").focus(); return; }
    const btn = $("g-create");
    btn.disabled = true;
    try {
      const res = await apiPost("/api/glossary", { name });
      $("g-name").value = "";
      toast(`Glossary “${name}” created.`, "ok");
      await load(res.id);
      $("g-src").focus();
    } catch (e) {
      showError(`Could not create glossary: ${humanError(e)}`);
      toast(humanError(e), "fail");
    } finally {
      btn.disabled = false;
    }
  }

  async function deleteStore() {
    const st = current();
    if (!st) return;
    if (!confirm(`Delete glossary “${st.name}” and its ${st.entries.length} entries?`)) return;
    try {
      await apiDelete(`/api/glossary/${encodeURIComponent(st.id)}`);
      state.selectedId = null;
      toast("Glossary deleted.", "ok");
      await load();
    } catch (e) {
      showError(`Could not delete glossary: ${humanError(e)}`);
      toast(humanError(e), "fail");
    }
  }

  async function addEntry() {
    const st = current();
    if (!st) { toast("Select a glossary first.", "warn"); return; }
    const source = $("g-src").value.trim();
    const target = $("g-tgt").value.trim();
    if (!source || !target) { toast("Both a source and a target term are required.", "warn"); return; }
    const btn = $("g-add");
    btn.disabled = true;
    try {
      const entry = {
        source_term: source,
        target_term: target,
        source_lang: $("g-slang").value,
        target_lang: $("g-tlang").value,
      };
      await apiPost(`/api/glossary/${encodeURIComponent(st.id)}/entries`, entry);
      $("g-src").value = "";
      $("g-tgt").value = "";
      toast("Entry added.", "ok");
      await load(st.id);
      $("g-src").focus();
    } catch (e) {
      showError(`Could not add entry: ${humanError(e)}`);
      toast(humanError(e), "fail");
    } finally {
      btn.disabled = false;
    }
  }

  $("g-create").addEventListener("click", createStore);
  $("g-name").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); void createStore(); } });
  $("g-del").addEventListener("click", deleteStore);
  $("g-add").addEventListener("click", addEntry);
  $("g-refresh").addEventListener("click", () => load());
  for (const id of ["g-src", "g-tgt"]) {
    $(id).addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); void addEntry(); } });
  }

  (async () => {
    await fillLangSelect($("g-slang"), { selected: "EN", baseOnly: true });
    await fillLangSelect($("g-tlang"), { selected: "DE", baseOnly: true });
    await load();
  })();

  return () => {};
}
