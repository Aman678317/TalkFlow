import React from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../stores/auth";
import { Badge } from "./ui";

export function Logo({ className = "h-8 w-8" }: { className?: string }) {
  return <img src="/logo.svg" alt="GlobalTalk AI" className={className} />;
}

const NAV = [
  { to: "/dashboard", label: "Dashboard", icon: "◧" },
  { to: "/translate", label: "Translate", icon: "⇄" },
  { to: "/documents", label: "Documents", icon: "▤" },
  { to: "/meetings", label: "Meetings", icon: "◉" },
  { to: "/chat", label: "Chat rooms", icon: "💬" },
  { to: "/history", label: "History", icon: "⧗" },
  { to: "/glossaries", label: "Glossaries", icon: "❡" },
  { to: "/translation-memory", label: "Translation memory", icon: "⛁" },
  { to: "/style-profiles", label: "Style profiles", icon: "✎" },
  { to: "/api", label: "API keys", icon: "⚿" },
  { to: "/usage", label: "Usage", icon: "∿" },
  { to: "/billing", label: "Billing", icon: "◇" },
  { to: "/team", label: "Team", icon: "👥" },
  { to: "/settings", label: "Settings", icon: "⚙" },
  { to: "/admin", label: "Admin", icon: "⌘", adminOnly: true },
];

export default function Layout() {
  const { user, org, role, logout } = useAuth();
  const nav = useNavigate();
  const [open, setOpen] = React.useState(false);

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <aside className={`fixed inset-y-0 left-0 z-40 flex w-60 flex-col bg-ink-950 text-ink-200
                          transition-transform lg:static lg:translate-x-0
                          ${open ? "translate-x-0" : "-translate-x-full"}`}
             aria-label="Main navigation">
        <div className="flex items-center gap-2.5 px-5 py-4">
          <Logo className="h-7 w-7" />
          <div>
            <p className="text-sm font-bold tracking-tight text-white">GlobalTalk <span className="text-signal-400">AI</span></p>
            <p className="text-[10px] uppercase tracking-widest text-ink-400">One conversation, every language</p>
          </div>
        </div>
        <nav className="flex-1 overflow-y-auto px-2 py-2">
          {NAV.filter((n) => !n.adminOnly || user?.is_platform_admin).map((n) => (
            <NavLink key={n.to} to={n.to} onClick={() => setOpen(false)}
              className={({ isActive }) =>
                `mb-0.5 flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] font-medium transition ${
                  isActive ? "bg-signal-600/20 text-signal-300" : "text-ink-300 hover:bg-ink-900 hover:text-white"}`}>
              <span aria-hidden className="w-4 text-center text-xs opacity-80">{n.icon}</span>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-ink-900 p-3">
          <div className="flex items-center gap-2.5 rounded-lg px-2 py-1.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-signal-600 text-xs font-bold text-white"
                 aria-hidden>
              {(user?.full_name || user?.email || "?").slice(0, 1).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-semibold text-white">{user?.full_name || user?.email}</p>
              <p className="truncate text-[10px] text-ink-400">{org?.name} · {role}</p>
            </div>
          </div>
          <button onClick={async () => { await logout(); nav("/login"); }}
                  className="mt-1 w-full rounded-lg px-3 py-1.5 text-left text-xs text-ink-400 hover:bg-ink-900 hover:text-white">
            Sign out
          </button>
        </div>
      </aside>
      {open && <div className="fixed inset-0 z-30 bg-black/40 lg:hidden" onClick={() => setOpen(false)} />}

      {/* Main */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-ink-100 bg-white/80 px-4 py-2.5 backdrop-blur lg:px-6">
          <button className="rounded-lg p-2 text-ink-500 hover:bg-ink-100 lg:hidden"
                  onClick={() => setOpen(true)} aria-label="Open navigation">☰</button>
          <div className="flex-1" />
          {org && <Badge tone="info" title="Current organization plan">{org.plan.toUpperCase()}</Badge>}
          <a href="/api-docs" className="hidden text-xs font-medium text-ink-400 hover:text-ink-700 sm:block"
             target="_blank" rel="noreferrer">API docs ↗</a>
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
