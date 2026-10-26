import { apiGet, apiPost, esc, humanError, fmtNum } from "../api.mjs";
import { getKey, hasVault } from "../vault.mjs";

export function render(root) {
  root.innerHTML = `
  <div class="view">
    <div class="row">
      <h2 class="view-title">Usage</h2>
      <span id="u-updated" class="muted"></span>
      <span class="spacer"></span>
      <button id="u-refresh" class="btn ghost sm" type="button">Refresh</button>
    </div>
    <div id="u-error" class="banner fail" hidden></div>
    <div class="stat-grid">
      <div class="stat"><div class="lbl">Characters today</div><div class="big" id="u-chars">—</div><div class="muted">demo / local engine</div></div>
      <div class="stat"><div class="lbl">Translations</div><div class="big" id="u-translations">—</div><div class="muted">since server boot</div></div>
      <div class="stat"><div class="lbl">Corrections</div><div class="big" id="u-corrections">—</div><div class="muted">since server boot</div></div>
    </div>
    <div class="card">
      <h3>Local activity</h3>
      <div class="meter">
        <div class="meter-head"><span>Translations</span><span class="num" id="u-tr-num">—</span></div>
        <div class="progress"><div class="bar" id="u-tr-bar"></div></div>
      </div>
      <div class="meter">
        <div class="meter-head"><span>Corrections</span><span class="num" id="u-co-num">—</span></div>
        <div class="progress"><div class="bar" id="u-co-bar"></div></div>
      </div>
      <p class="usage-note">Local counters are in-memory on the server and reset when it restarts. Bars are relative to the busier of the two actions.</p>
    </div>
    <div class="card">
      <h3>DeepL live quota</h3>
      <div id="u-live-empty" class="empty">Checking for a DeepL key…</div>
      <div id="u-live" hidden>
        <div id="u-live-chips" class="chips"></div>
        <div class="meter">
          <div class="meter-head"><span>Characters used</span><span class="num" id="u-live-num"></span></div>
          <div class="progress"><div class="bar" id="u-live-bar"></div></div>
        </div>
        <p class="usage-note" id="u-live-note"></p>
      </div>
    </div>
  </div>`;

  const $ = (id) => root.querySelector("#" + id);
  let busy = false;

  function showError(message) {
    $("u-error").hidden = !message;
    $("u-error").textContent = message || "";
  }

  function paintLiveEmpty(message) {
    $("u-live").hidden = true;
    $("u-live-empty").hidden = false;
    $("u-live-empty").textContent = message;
  }

  function paintLive(res, usedVaultKey) {
    $("u-live-empty").hidden = true;
    $("u-live").hidden = false;

    const count = res.character_count == null ? NaN : Number(res.character_count);
    const limit = res.character_limit == null ? NaN : Number(res.character_limit);
    const hasCount = Number.isFinite(count) && count >= 0;
    const hasLimit = Number.isFinite(limit) && limit > 0;

    const chips = [];
    if (res.tier) chips.push(`<span class="chip info">${esc(res.tier)} tier</span>`);
    if (res.host) chips.push(`<span class="chip">${esc(res.host)}</span>`);
    chips.push(`<span class="chip">${usedVaultKey ? "vault key" : "server env key"}</span>`);
    if (res.live_check) chips.push(`<span class="chip warn">live check: ${esc(res.live_check)}</span>`);
    $("u-live-chips").innerHTML = chips.join("");

    if (!hasCount) {
      $("u-live-num").textContent = "unavailable";
      $("u-live-bar").style.width = "0";
      $("u-live-bar").className = "bar";
      $("u-live-note").textContent = res.live_check === "failed"
        ? "The live check failed (network or upstream error), so character usage cannot be shown right now."
        : "The server did not return a character count for this key.";
      return;
    }

    $("u-live-num").textContent = hasLimit ? `${fmtNum(count)} / ${fmtNum(limit)} chars` : `${fmtNum(count)} chars used`;
    if (hasLimit) {
      const ratio = Math.max(0, Math.min(1, count / limit));
      const bar = $("u-live-bar");
      bar.style.width = `${(ratio * 100).toFixed(1)}%`;
      bar.className = `bar${ratio > 0.9 ? " low" : ""}`;
      $("u-live-note").textContent = `${(ratio * 100).toFixed(1)}% of the monthly character limit used (${fmtNum(limit - count)} remaining).`;
    } else {
      $("u-live-bar").style.width = "0";
      $("u-live-bar").className = "bar";
      $("u-live-note").textContent = "The server returned a character count but no limit — the quota bar is unavailable.";
    }
  }

  async function loadLocal() {
    try {
      const d = await apiGet("/api/usage");
      const local = d.local && typeof d.local === "object" ? d.local : {};
      const chars = Number(local.chars_today) || 0;
      const translations = Number(local.translations) || 0;
      const corrections = Number(local.corrections) || 0;
      $("u-chars").textContent = fmtNum(chars);
      $("u-translations").textContent = fmtNum(translations);
      $("u-corrections").textContent = fmtNum(corrections);
      const max = Math.max(translations, corrections, 1);
      $("u-tr-num").textContent = `${fmtNum(translations)} / ${fmtNum(translations + corrections)} actions`;
      $("u-co-num").textContent = `${fmtNum(corrections)} / ${fmtNum(translations + corrections)} actions`;
      $("u-tr-bar").style.width = `${Math.round((translations / max) * 100)}%`;
      $("u-co-bar").style.width = `${Math.round((corrections / max) * 100)}%`;
    } catch (e) {
      showError(`Could not load local usage: ${humanError(e)}`);
    }
  }

  async function loadLive() {
    const key = getKey();
    let res;
    try {
      res = await apiPost("/api/deepl/usage", {}, key ? { key, timeoutMs: 25000 } : { timeoutMs: 25000 });
    } catch (e) {
      if (e.status === 400) {
        if (e.data?.valid === false) {
          paintLiveEmpty(`The configured DeepL key was rejected by the server (${e.data?.reason || "invalid format"}). Re-save it in Settings.`);
        } else if (hasVault()) {
          paintLiveEmpty("An encrypted vault exists but is locked in this tab. Unlock it in Settings to query your live DeepL quota.");
        } else {
          paintLiveEmpty("DeepL is not configured. Add a key in Settings to see live quota — local demo counters still work.");
        }
      } else {
        paintLiveEmpty(`Live quota unavailable: ${humanError(e)}`);
      }
      return;
    }

    let count = res.character_count == null ? NaN : Number(res.character_count);
    let limit = res.character_limit == null ? NaN : Number(res.character_limit);
    // Server currently nulls character_limit in /api/deepl/usage; validate returns it, so retry once.
    if (Number.isFinite(count) && !(Number.isFinite(limit) && limit > 0)) {
      try {
        const v = await apiPost("/api/deepl/validate", {}, key ? { key, timeoutMs: 20000 } : { timeoutMs: 20000 });
        const vLimit = v.character_limit == null ? NaN : Number(v.character_limit);
        if (Number.isFinite(vLimit) && vLimit > 0) {
          limit = vLimit;
          if (Number.isFinite(Number(v.character_count))) count = Number(v.character_count);
        }
      } catch { /* keep the partial usage response */ }
    }
    paintLive({ ...res, character_count: count, character_limit: limit }, Boolean(key));
  }

  async function refresh() {
    if (busy) return;
    busy = true;
    $("u-refresh").disabled = true;
    showError("");
    try {
      await Promise.all([loadLocal(), loadLive()]);
      $("u-updated").textContent = `Updated ${new Date().toLocaleTimeString()}`;
    } finally {
      busy = false;
      $("u-refresh").disabled = false;
    }
  }

  $("u-refresh").addEventListener("click", refresh);
  void refresh();
  return () => {};
}
