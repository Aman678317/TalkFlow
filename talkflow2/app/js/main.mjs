// Hash router + shell behavior for TalkFlow 2.0. All actual features live in ./views/*.mjs.
import { apiGet, esc } from "./api.mjs";
import { render as translatorView } from "./views/translator.mjs";
import { render as writeView } from "./views/write.mjs";
import { render as voiceView } from "./views/voice.mjs";
import { render as documentsView } from "./views/documents.mjs";
import { render as glossaryView } from "./views/glossary.mjs";
import { render as usageView } from "./views/usage.mjs";
import { render as settingsView } from "./views/settings.mjs";
import { render as testsView } from "./views/tests.mjs";

const ROUTES = new Map([
  ["#/translate", { view: translatorView, label: "Translate" }],
  ["#/write", { view: writeView, label: "Write" }],
  ["#/voice", { view: voiceView, label: "Voice" }],
  ["#/documents", { view: documentsView, label: "Documents" }],
  ["#/glossary", { view: glossaryView, label: "Glossary" }],
  ["#/usage", { view: usageView, label: "Usage" }],
  ["#/settings", { view: settingsView, label: "Settings" }],
  ["#/tests", { view: testsView, label: "Tests" }],
]);
const DEFAULT_ROUTE = "#/translate";
const THEME_KEY = "talkflow.theme";
let teardown = null;
let healthTimer = null;

function applyTheme(next, { persist = true } = {}) {
  const theme = next === "light" ? "light" : "dark";
  document.documentElement.dataset.theme = theme;
  if (persist) localStorage.setItem(THEME_KEY, theme);
  document.dispatchEvent(new CustomEvent("talkflow:theme", { detail: theme }));
}

document.getElementById("theme-toggle").addEventListener("click", () => {
  applyTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light");
});

async function healthPing() {
  const dot = document.getElementById("api-dot");
  if (!dot) return;
  try {
    const h = await apiGet("/api/health", { timeoutMs: 8000 });
    const ok = h && h.status === "ok";
    dot.className = `api-dot ${ok ? "ok" : "down"}`;
    dot.textContent = ok ? "API live" : "API unhealthy";
    dot.title = ok
      ? `Engine ${h.version || ""} · ${h.agents} agents · uptime ${Math.round((h.uptime_ms || 0) / 1000)} s`
      : "API responded but reported problems";
  } catch {
    dot.className = "api-dot down";
    dot.textContent = "API offline";
    dot.title = "The TalkFlow server is not reachable — run `npm start` in talkflow2/";
  }
}

function renderRoute() {
  const hash = location.hash || DEFAULT_ROUTE;
  const route = ROUTES.get(hash);
  if (!route) { history.replaceState(null, "", DEFAULT_ROUTE); renderRoute(); return; }
  if (typeof teardown === "function") {
    try { teardown(); } catch { /* a view's cleanup must never block navigation */ }
  }
  teardown = null;
  const main = document.getElementById("main");
  main.innerHTML = "";
  for (const a of document.querySelectorAll("#nav a")) {
    a.classList.toggle("on", a.getAttribute("href") === hash);
    if (a.getAttribute("href") === hash) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
  document.title = `TalkFlow 2.0 · ${route.label}`;
  try {
    const t = route.view(main);
    teardown = typeof t === "function" ? t : null;
  } catch (e) {
    main.innerHTML = `<div class="view"><div class="card"><h2 class="view-title">This view failed to render</h2>
      <p class="empty">${esc(e.message)}</p>
      <p class="empty">If engine modules are still being built, make sure <code>/engine/key-vault.mjs</code> and <code>/engine/subtitles.mjs</code> exist.</p></div></div>`;
  }
  window.scrollTo(0, 0);
}

function boot() {
  applyTheme(localStorage.getItem(THEME_KEY) === "light" ? "light" : "dark", { persist: false });
  if (!ROUTES.has(location.hash)) history.replaceState(null, "", DEFAULT_ROUTE);
  window.addEventListener("hashchange", renderRoute);
  renderRoute();
  healthPing();
  clearInterval(healthTimer);
  healthTimer = setInterval(healthPing, 30000);
  document.getElementById("api-dot")?.addEventListener("click", healthPing);
}

boot();
