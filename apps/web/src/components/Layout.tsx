import React from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "motion/react";
import { useAuth } from "../stores/auth";
import { PageTransition } from "./Motion";
import { springSoft } from "../lib/motion";

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
              className="mt-2 inline-flex items-center rounded-lg bg-rose-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-xs transition-[background-color,transform] hover:bg-rose-700 active:scale-95"
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
  const location = useLocation();
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
    <div className="flex h-full min-h-0 bg-[#F4F6F8] text-neutral-900 font-sans">
      {/* ── Sidebar (Apple HIG iPadOS / macOS Navigation) ─────────────── */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex flex-col border-r border-black/[0.08] bg-[#FBFBFD] shadow-sm transition-transform duration-300 ease-emphasized lg:static lg:translate-x-0
                    ${open ? "translate-x-0" : "-translate-x-full"}`}
        style={{ width: "var(--sidebar-w, 240px)" }}
        aria-label="Main navigation"
      >
        {/* Brand */}
        <div className="flex items-center gap-3 border-b border-black/[0.06] px-5 py-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-[#007AFF] shadow-xs">
            <Logo className="h-5 w-5 brightness-0 invert" />
          </div>
          <div>
            <p className="text-[13px] font-semibold tracking-[-0.015em] text-neutral-950 leading-tight">
              GlobalTalk <span className="text-[#007AFF]">AI</span>
            </p>
            <p className="text-[9px] font-semibold uppercase tracking-widest text-neutral-400 leading-tight mt-0.5">
              Every language
            </p>
          </div>
        </div>

        {/* Nav groups */}
        <nav className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-4">
          {NAV_GROUPS.map((group, index) => {
            const items = group.items
              .map((p) => byPath[p])
              .filter(Boolean);
            const isCollapsible = group.label === "Tools" || group.label === "Account";
            const isCollapsed = Boolean(collapsedGroups[group.label]);

            return (
              <div key={group.label} className={index > 0 ? "border-t border-black/[0.06] pt-3" : ""}>
                <div className="mb-1 flex items-center justify-between px-3">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-neutral-400">
                    {group.label}
                  </p>
                  {isCollapsible && (
                    <button
                      type="button"
                      onClick={() => toggleGroup(group.label)}
                      aria-expanded={!isCollapsed}
                      aria-label={`${isCollapsed ? "Expand" : "Collapse"} ${group.label} category`}
                      className="flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-medium text-neutral-400 transition-colors hover:bg-black/[0.04] hover:text-neutral-700"
                    >
                      <span>{isCollapsed ? "Show" : "Hide"}</span>
                      <ChevronDown className={`h-3 w-3 transition-transform duration-200 ${isCollapsed ? "-rotate-90" : "rotate-0"}`} />
                    </button>
                  )}
                </div>
                <AnimatePresence initial={false}>
                  {!isCollapsed && (
                    <motion.div
                      key="group-items"
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={springSoft}
                      className="overflow-hidden space-y-0.5"
                    >
                      {items.map(({ to, label, Icon }) => (
                        <NavLink
                          key={to}
                          to={to}
                          onClick={() => setOpen(false)}
                          className={({ isActive }) =>
                             `group flex items-center gap-2.5 rounded-xl px-3 py-2 text-[13px] font-medium transition-all duration-150 active:scale-[0.98]
                              ${isActive
                                ? "bg-[#007AFF] text-white shadow-xs font-semibold"
                                : "text-neutral-700 hover:bg-black/[0.05] hover:text-neutral-950"}`
                          }
                        >
                          {({ isActive }) => (
                            <>
                               <Icon className={`h-4 w-4 shrink-0 transition-colors ${isActive ? "text-white" : "text-neutral-400 group-hover:text-neutral-700"}`} />
                              <span className="truncate">{label}</span>
                            </>
                          )}
                        </NavLink>
                      ))}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          })}
        </nav>

        {/* User footer */}
        <div className="mt-auto shrink-0 border-t border-black/[0.06] p-3">
          <div className="flex items-center gap-2.5 rounded-2xl border border-black/[0.06] bg-black/[0.02] p-2.5">
            <div
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#007AFF] text-xs font-bold text-white shadow-xs"
              aria-hidden
            >
              {(user?.full_name || user?.email || "?").slice(0, 1).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-semibold text-neutral-900 leading-tight">
                {user?.full_name || user?.email}
              </p>
              <p
                title={`${org?.name ?? ""} · ${role ?? ""}`}
                className="text-[11px] text-neutral-500 leading-tight mt-0.5 truncate"
              >
                {org?.name || "GlobalTalk"} · {role || "member"}
              </p>
            </div>
          </div>
          <button
            onClick={async () => { await logout(); nav("/login"); }}
            className="group mt-2 flex w-full items-center gap-2.5 rounded-xl px-3 py-1.5 text-xs font-medium text-neutral-500 transition-colors hover:bg-black/[0.04] hover:text-neutral-900"
          >
            <LogOut className="h-3.5 w-3.5 shrink-0 text-neutral-400 group-hover:text-neutral-600 transition-colors" aria-hidden="true" />
            <span>Sign out</span>
          </button>
        </div>
      </aside>

      {/* Overlay (mobile) */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-30 bg-black/40 backdrop-blur-sm lg:hidden"
            onClick={() => setOpen(false)}
          />
        )}
      </AnimatePresence>

      {/* ── Main content ────────────────────────────────────────── */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top bar — frosted material (Apple HIG) */}
        <header className="material-bar sticky top-0 z-20 backdrop-blur-xl bg-white/80 border-b border-black/[0.06]">
          <div className="mx-auto flex max-w-5xl items-center justify-between gap-3 px-4 py-2.5 lg:px-6">
            <button
              className="rounded-xl p-2 text-neutral-600 transition-colors hover:bg-black/[0.05] lg:hidden"
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
                <span className="apple-pill-badge">
                  {org.plan}
                </span>
              )}
              <a
                href="/api/docs"
                className="inline-flex min-h-[32px] items-center gap-1.5 rounded-full border border-black/[0.06] bg-white px-3 py-1 text-xs font-medium text-neutral-700 shadow-xs transition-colors hover:bg-black/[0.03] hover:text-neutral-950"
                target="_blank"
                rel="noreferrer"
              >
                <span>API docs</span>
                <ExternalLink className="h-3 w-3 text-neutral-400" />
              </a>
            </div>
          </div>
        </header>

        {/* Page content — keyed route transitions (skipped for reduced motion via MotionConfig) */}
        <main className="min-h-0 flex-1 overflow-y-auto">
          <ErrorBoundary>
            <AnimatePresence mode="wait" initial={false}>
              <PageTransition key={location.pathname} className="h-full">
                <Outlet />
              </PageTransition>
            </AnimatePresence>
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
