import React from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../stores/auth";

import {
  LayoutDashboard, ArrowLeftRight, PenLine, Mic2, FileText,
  Video, MessageSquare, Clock, BookOpen, Database, Sliders,
  KeyRound, BarChart2, CreditCard, Users, Settings, Shield,
  ChevronDown, LogOut, ExternalLink,
} from "lucide-react";

export function Logo({ className = "h-8 w-8" }: { className?: string }) {
  return <img src="/logo.svg" alt="GlobalTalk AI" className={className} />;
}

const NAV = [
  { to: "/dashboard",          label: "Dashboard",          Icon: LayoutDashboard },
  { to: "/translate",          label: "Translate",          Icon: ArrowLeftRight },
  { to: "/write",              label: "Write",              Icon: PenLine },
  { to: "/voice",              label: "Voice",              Icon: Mic2 },
  { to: "/documents",          label: "Documents",          Icon: FileText },
  { to: "/meetings",           label: "Meetings",           Icon: Video },
  { to: "/chat",               label: "Chat rooms",         Icon: MessageSquare },
  { to: "/history",            label: "History",            Icon: Clock },
  { to: "/glossaries",         label: "Glossaries",         Icon: BookOpen },
  { to: "/translation-memory", label: "Translation memory", Icon: Database },
  { to: "/style-profiles",     label: "Style profiles",     Icon: Sliders },
  { to: "/api",                label: "API keys",           Icon: KeyRound },
  { to: "/usage",              label: "Usage",              Icon: BarChart2 },
  { to: "/billing",            label: "Billing",            Icon: CreditCard },
  { to: "/team",               label: "Team",               Icon: Users },
  { to: "/settings",           label: "Settings",           Icon: Settings },
  { to: "/admin",              label: "Admin",              Icon: Shield, adminOnly: true },
];

const NAV_GROUPS = [
  {
    label: "Translate",
    items: ["/dashboard", "/translate", "/write", "/documents", "/history"],
  },
  {
    label: "Communication",
    items: ["/voice", "/meetings", "/chat"],
  },
  {
    label: "Tools",
    items: ["/glossaries", "/translation-memory", "/style-profiles"],
  },
  {
    label: "Account",
    items: ["/api", "/usage", "/billing", "/team", "/settings", "/admin"],
  },
];

interface ErrorBoundaryProps {
  children: React.ReactNode;
}
interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("ErrorBoundary caught an error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex h-full items-center justify-center p-6">
          <div className="max-w-md w-full rounded-2xl border border-rose-200 bg-rose-50/70 p-6 text-center space-y-3">
            <h2 className="text-base font-semibold text-rose-900">An error occurred in this view</h2>
            <p className="text-xs text-rose-700 font-mono break-words">{this.state.error?.message || "Unknown error"}</p>
            <button
              onClick={() => { this.setState({ hasError: false, error: null }); window.location.reload(); }}
              className="mt-2 inline-flex items-center rounded-lg bg-rose-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-xs hover:bg-rose-700 active:scale-95 transition-all"
            >
              Reload View
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function Layout() {
  const { user, org, role, logout } = useAuth();
  const nav = useNavigate();
  const [open, setOpen] = React.useState(false);
  const [collapsedGroups, setCollapsedGroups] = React.useState<Record<string, boolean>>({
    Tools: false,
    Account: true,
  });

  const toggleGroup = (groupLabel: string) => {
    setCollapsedGroups((prev) => ({
      ...prev,
      [groupLabel]: !prev[groupLabel],
    }));
  };

  const allNav = NAV.filter((n) => !n.adminOnly || user?.is_platform_admin);
  const byPath = Object.fromEntries(allNav.map((n) => [n.to, n]));

  return (
    <div className="flex h-full bg-[#F8F9FA]">
      {/* ── Sidebar ─────────────────────────────────────────────── */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex flex-col bg-dl-navy transition-transform duration-200 lg:static lg:translate-x-0 border-r border-white/[.08] shadow-sm
                    ${open ? "translate-x-0" : "-translate-x-full"}`}
        style={{ width: "var(--sidebar-w, 240px)" }}
        aria-label="Main navigation"
      >
        {/* Brand */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-white/[.08]">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-dl-blue shadow-sm">
            <Logo className="h-5 w-5 brightness-0 invert" />
          </div>
          <div>
            <p className="text-[13px] font-bold tracking-tight text-white leading-tight">
              GlobalTalk <span className="text-blue-400">AI</span>
            </p>
            <p className="text-[9px] font-medium uppercase tracking-widest text-white/40 leading-tight mt-0.5">
              Every language
            </p>
          </div>
        </div>

        {/* Nav groups */}
        <nav className="flex-1 min-h-0 overflow-y-auto px-3 py-3 space-y-3">
          {NAV_GROUPS.map((group, index) => {
            const items = group.items
              .map((p) => byPath[p])
              .filter(Boolean);
            const isCollapsible = group.label === "Tools" || group.label === "Account";
            const isCollapsed = Boolean(collapsedGroups[group.label]);

            return (
              <div key={group.label} className={index > 0 ? "pt-2.5 border-t border-white/[.07]" : ""}>
                <div className="flex items-center justify-between mb-1 px-3">
                  <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-white/40">
                    {group.label}
                  </p>
                  {isCollapsible && (
                    <button
                      type="button"
                      onClick={() => toggleGroup(group.label)}
                      aria-expanded={!isCollapsed}
                      aria-label={`${isCollapsed ? "Expand" : "Collapse"} ${group.label} category`}
                      className="flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-medium text-white/40 hover:bg-white/[.08] hover:text-white transition-colors"
                    >
                      <span>{isCollapsed ? "Show" : "Hide"}</span>
                      <ChevronDown className={`h-3 w-3 transition-transform duration-200 ${isCollapsed ? "-rotate-90" : "rotate-0"}`} />
                    </button>
                  )}
                </div>
                {!isCollapsed && items.map(({ to, label, Icon }) => (
                  <NavLink
                    key={to}
                    to={to}
                    onClick={() => setOpen(false)}
                    className={({ isActive }) =>
                      `group flex items-center gap-3 rounded-xl px-3 py-2 text-[13px] font-medium transition-all duration-150 mb-0.5 active:scale-[0.98]
                       ${isActive
                         ? "bg-dl-blue text-white shadow-xs"
                         : "text-white/60 hover:bg-white/[.07] hover:text-white"}`
                    }
                  >
                    {({ isActive }) => (
                      <>
                        <Icon className={`h-4 w-4 shrink-0 transition-colors ${isActive ? "text-white" : "text-white/40 group-hover:text-white/80"}`} />
                        <span className="truncate">{label}</span>
                      </>
                    )}
                  </NavLink>
                ))}
              </div>
            );
          })}
        </nav>

        {/* User footer */}
        <div className="shrink-0 mt-auto border-t border-white/[.08] p-3">
          <div className="flex items-center gap-2.5 rounded-xl bg-white/[.04] border border-white/[.06] p-2.5">
            <div
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-dl-blue text-xs font-bold text-white shadow-xs"
              aria-hidden
            >
              {(user?.full_name || user?.email || "?").slice(0, 1).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-semibold text-white leading-tight">
                {user?.full_name || user?.email}
              </p>
              <p
                title={`${org?.name ?? ""} · ${role ?? ""}`}
                className="text-[11px] text-white/50 leading-tight mt-0.5 truncate"
              >
                {org?.name || "GlobalTalk"} · {role || "member"}
              </p>
            </div>
          </div>
          <button
            onClick={async () => { await logout(); nav("/login"); }}
            className="group mt-2 flex w-full items-center gap-2.5 rounded-xl px-3 py-1.5 text-xs font-medium text-white/50 hover:bg-white/[.07] hover:text-white transition-all"
          >
            <LogOut className="h-3.5 w-3.5 shrink-0 text-white/40 group-hover:text-white/70 transition-colors" aria-hidden="true" />
            <span>Sign out</span>
          </button>
        </div>
      </aside>

      {/* Overlay (mobile) */}
      {open && (
        <div
          className="fixed inset-0 z-30 bg-black/40 backdrop-blur-sm lg:hidden transition-opacity"
          onClick={() => setOpen(false)}
        />
      )}

      {/* ── Main content ────────────────────────────────────────── */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top bar */}
        <header className="border-b border-slate-200/80 bg-white/95 backdrop-blur-sm sticky top-0 z-20">
          <div className="mx-auto flex max-w-5xl items-center justify-between gap-3 px-4 py-2.5 lg:px-6">
            <button
              className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 lg:hidden transition-colors"
              onClick={() => setOpen(true)}
              aria-label="Open navigation"
            >
              <svg className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <div className="flex-1" />
            <div className="flex items-center gap-2.5">
              {org && (
                <span className="rounded-full border border-blue-200 bg-blue-50/80 px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wider text-dl-blue">
                  {org.plan}
                </span>
              )}
              <a
                href="/api/docs"
                className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 hover:text-dl-navy hover:bg-slate-50 transition-colors shadow-xs"
                target="_blank"
                rel="noreferrer"
              >
                <span>API docs</span>
                <ExternalLink className="h-3 w-3 text-slate-400" />
              </a>
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="min-h-0 flex-1 overflow-y-auto">
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
