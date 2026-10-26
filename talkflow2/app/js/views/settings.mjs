import { apiGet, apiPost, esc, toast, humanError, fmtNum } from "../api.mjs";
import { hasVault, getKey, maskKey, saveKey, unlock, deleteVault } from "../vault.mjs";

const PROV_KEY = "talkflow.provider";

export function render(root) {
  root.innerHTML = `
  <div class="view">
    <h2 class="view-title">Settings</h2>
    <div class="settings-grid">
      <div class="card">
        <h3>DeepL API key vault</h3>
        <p class="muted">Keys are encrypted with AES-GCM (PBKDF2, 150k iterations) and only ciphertext is written to localStorage. The passphrase and decrypted key live in this tab's memory; they are never rendered in full, put in a URL, or stored in plaintext.</p>
        <div id="s-key-state" class="chips"></div>
        <div class="row-form">
          <input id="s-key" type="password" autocomplete="new-password" placeholder="DeepL API key (free keys end with :fx)" aria-label="DeepL API key">
        </div>
        <div class="row-form">
          <input id="s-pass" type="password" autocomplete="new-password" placeholder="Vault passphrase (min 8 characters)" aria-label="Vault passphrase">
          <button id="s-save" class="btn primary" type="button">Save encrypted</button>
          <button id="s-unlock" class="btn" type="button">Unlock</button>
          <button id="s-revoke" class="btn danger" type="button">Revoke</button>
        </div>
        <div class="row">
          <button id="s-validate" class="btn" type="button">Validate key (live)</button>
          <span id="s-valid-msg" class="muted"></span>
        </div>
        <div id="s-live" class="chips"></div>
      </div>

      <div class="card">
        <h3>Preferences</h3>
        <div class="row-form">
          <span class="field-lbl">Provider</span>
          <div class="seg" id="s-provider" role="group" aria-label="Default provider">
            <button type="button" data-provider="local">Demo</button>
            <button type="button" data-provider="deepl">DeepL</button>
          </div>
          <span id="s-prov-hint" class="muted"></span>
        </div>
        <div class="row-form">
          <span class="field-lbl">Theme</span>
          <select id="s-theme" aria-label="Theme">
            <option value="dark">Dark</option>
            <option value="light">Light</option>
          </select>
        </div>
      </div>

      <div class="card">
        <h3>Server</h3>
        <div class="row-form">
          <span class="field-lbl">Origin</span>
          <input id="s-origin" type="text" readonly aria-label="Server origin">
          <span id="s-api" class="chip">checking…</span>
        </div>
        <p class="usage-note">The UI and API are same-origin; this build does not proxy to an external server URL. Requests always go to <code>/api/*</code>.</p>
      </div>

      <div class="card">
        <h3>About the agent pipeline</h3>
        <div id="s-agents-error" class="banner fail" hidden></div>
        <div id="s-agents" class="agent-grid"><div class="empty">Loading agents…</div></div>
      </div>
    </div>
  </div>`;

  const $ = (id) => root.querySelector("#" + id);
  const setMsg = (text, kind = "") => {
    const el = $("s-valid-msg");
    el.textContent = text;
    el.className = kind === "fail" ? "error-text" : kind === "warn" ? "warn-text" : "muted";
  };

  function paintState() {
    const exists = hasVault();
    const key = getKey();
    const chips = [exists ? `<span class="chip ok">vault stored</span>` : `<span class="chip">no vault yet</span>`];
    if (key) {
      chips.push(`<span class="chip info masked-chip">${esc(maskKey(key))}</span><span class="chip ok">unlocked for this tab</span>`);
    } else if (exists) {
      chips.push(`<span class="chip warn">locked</span>`);
    } else {
      chips.push(`<span class="chip">not configured</span>`);
    }
    chips.push(`<span class="chip">AES-GCM · PBKDF2</span>`);
    $("s-key-state").innerHTML = chips.join("");
    $("s-validate").disabled = !key;
    $("s-revoke").disabled = !exists;
    $("s-unlock").disabled = !exists;
  }

  function paintProvider() {
    const provider = localStorage.getItem(PROV_KEY) === "deepl" ? "deepl" : "local";
    for (const b of $("s-provider").querySelectorAll("button")) {
      b.classList.toggle("on", b.dataset.provider === provider);
      b.setAttribute("aria-pressed", String(b.dataset.provider === provider));
    }
    const hint = $("s-prov-hint");
    if (provider === "deepl") {
      hint.className = !getKey() ? "warn-text" : "muted";
      hint.textContent = getKey()
        ? "DeepL requests use the unlocked vault key."
        : hasVault() ? "Vault locked — unlock it to use DeepL." : "No key stored — DeepL requests will fail until you save one.";
    } else {
      hint.className = "muted";
      hint.textContent = "Demo engine runs locally on the server; DeepL is optional.";
    }
  }

  async function save() {
    const key = $("s-key").value.trim();
    const pass = $("s-pass").value;
    if (!key) { setMsg("Enter a DeepL API key first.", "fail"); $("s-key").focus(); return; }
    if (pass.length < 8) { setMsg("Use a vault passphrase of at least 8 characters.", "fail"); $("s-pass").focus(); return; }
    $("s-save").disabled = true;
    try {
      await saveKey(key, pass);
      $("s-key").value = "";
      $("s-pass").value = "";
      $("s-live").innerHTML = "";
      paintState();
      paintProvider();
      setMsg("Key encrypted and saved. It stays unlocked until this tab reloads.", "ok");
      toast("API key encrypted and saved locally.", "ok");
    } catch (e) {
      setMsg(`Could not encrypt the key: ${e.message}`, "fail");
      toast(`Could not save the key: ${e.message}`, "fail");
    } finally {
      $("s-save").disabled = false;
    }
  }

  async function unlockVault() {
    const pass = $("s-pass").value;
    if (!hasVault()) { setMsg("There is no vault to unlock — save a key first.", "fail"); return; }
    if (!pass) { setMsg("Enter the vault passphrase.", "fail"); $("s-pass").focus(); return; }
    $("s-unlock").disabled = true;
    try {
      await unlock(pass);
      $("s-pass").value = "";
      $("s-live").innerHTML = "";
      paintState();
      paintProvider();
      setMsg("Vault unlocked for this tab.", "ok");
      toast("Vault unlocked. The key stays in memory only.", "ok");
    } catch {
      setMsg("Wrong passphrase or corrupted vault — try again.", "fail");
      toast("Wrong passphrase or corrupted vault.", "fail");
    } finally {
      $("s-unlock").disabled = !hasVault();
    }
  }

  function revoke() {
    if (!hasVault()) return;
    if (!confirm("Delete the encrypted vault from this browser? The key cannot be recovered without re-entering it.")) return;
    deleteVault();
    $("s-key").value = "";
    $("s-pass").value = "";
    $("s-live").innerHTML = "";
    paintState();
    paintProvider();
    setMsg("Encrypted vault deleted. DeepL is no longer configured in this browser.", "ok");
    toast("Encrypted vault revoked.", "ok");
  }

  async function validate() {
    const key = getKey();
    if (!key) { setMsg(hasVault() ? "Unlock the vault first." : "Save a key first.", "fail"); return; }
    const btn = $("s-validate");
    btn.disabled = true;
    setMsg("Validating against DeepL…");
    try {
      const res = await apiPost("/api/deepl/validate", {}, { key, timeoutMs: 25000 });
      const chips = [`<span class="chip ok">valid</span>`, `<span class="chip">${esc(maskKey(key))}</span>`];
      if (res.tier) chips.push(`<span class="chip info">${esc(res.tier)} tier</span>`);
      if (res.host) chips.push(`<span class="chip">${esc(res.host)}</span>`);
      const count = res.character_count == null ? NaN : Number(res.character_count);
      const limit = res.character_limit == null ? NaN : Number(res.character_limit);
      if (Number.isFinite(count) && Number.isFinite(limit) && limit > 0) {
        chips.push(`<span class="chip">${fmtNum(count)} / ${fmtNum(limit)} chars</span>`);
        chips.push(`<span class="chip">${((count / limit) * 100).toFixed(1)}% used</span>`);
      } else if (Number.isFinite(count)) {
        chips.push(`<span class="chip">${fmtNum(count)} chars used</span>`);
      }
      if (res.live_check) chips.push(`<span class="chip warn">live check: ${esc(res.live_check)}</span>`);
      $("s-live").innerHTML = chips.join("");
      setMsg(
        res.live_check === "failed"
          ? "Key format is valid, but the live check failed (network or upstream)."
          : "Key validated live against DeepL.",
        res.live_check === "failed" ? "warn" : "ok",
      );
    } catch (e) {
      if (e.data?.valid === false) {
        $("s-live").innerHTML = `<span class="chip fail">invalid</span><span class="chip">${esc(e.data.reason || "format")}</span>`;
        setMsg("The key was rejected — check it and re-save.", "fail");
      } else {
        setMsg(`Validation failed: ${humanError(e)}`, "fail");
      }
    } finally {
      btn.disabled = !getKey();
    }
  }

  $("s-save").addEventListener("click", save);
  $("s-unlock").addEventListener("click", unlockVault);
  $("s-revoke").addEventListener("click", revoke);
  $("s-validate").addEventListener("click", validate);
  $("s-key").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); void save(); } });
  $("s-pass").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); void unlockVault(); } });

  $("s-provider").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    localStorage.setItem(PROV_KEY, b.dataset.provider === "deepl" ? "deepl" : "local");
    paintProvider();
  });

  const themeSel = $("s-theme");
  const syncTheme = () => { themeSel.value = document.documentElement.dataset.theme === "light" ? "light" : "dark"; };
  syncTheme();
  themeSel.addEventListener("change", () => {
    const theme = themeSel.value === "light" ? "light" : "dark";
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("talkflow.theme", theme);
    document.dispatchEvent(new CustomEvent("talkflow:theme", { detail: theme }));
  });
  const onTheme = (e) => { themeSel.value = e.detail === "light" ? "light" : "dark"; };
  document.addEventListener("talkflow:theme", onTheme);

  $("s-origin").value = location.origin;
  apiGet("/api/health", { timeoutMs: 8000 }).then((h) => {
    const ok = h.status === "ok";
    $("s-api").className = `chip ${ok ? "ok" : "fail"}`;
    $("s-api").textContent = ok ? `live · v${h.version || "?"} · ${h.agents ?? 0} agents` : "unhealthy";
  }).catch((e) => {
    $("s-api").className = "chip fail";
    $("s-api").textContent = "offline";
    $("s-api").title = humanError(e);
  });

  apiGet("/api/agents", { timeoutMs: 10000 }).then((d) => {
    const agents = Array.isArray(d.agents) ? d.agents : [];
    if (!agents.length) {
      $("s-agents").innerHTML = `<div class="empty">The server reported no agents.</div>`;
      return;
    }
    $("s-agents").innerHTML = agents.map((a) => `
      <div class="agent-card">
        <strong>${esc(a.name || a.id || "agent")}</strong>
        <span class="chip info">${esc(a.id || "agent")}</span>
        ${a.version ? `<span class="chip">${esc(a.version)}</span>` : ""}
        <p class="muted">${esc(a.description || "")}</p>
      </div>`).join("");
  }).catch((e) => {
    $("s-agents-error").hidden = false;
    $("s-agents-error").textContent = `Could not load the agent manifest: ${humanError(e)}`;
    $("s-agents").innerHTML = "";
  });

  paintState();
  paintProvider();

  return () => document.removeEventListener("talkflow:theme", onTheme);
}
