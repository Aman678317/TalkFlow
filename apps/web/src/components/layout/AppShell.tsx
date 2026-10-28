import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { AnimatePresence } from 'motion/react';
import {
  BookmarkCheck, BookOpen, CreditCard, FileText, Files, Gauge, History, KeyRound, Languages,
  LayoutDashboard, Mic, MessageSquare, Phone, PhoneCall, PhoneIncoming, Settings as SettingsIcon,
  ShieldCheck, Sparkles, Users, Video,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '@/stores/auth';
import ErrorBoundary from '@/components/common/ErrorBoundary';
import { PageTransition } from '@/components/Motion';

const NAV = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/translate', label: 'Translate', icon: Languages },
  { to: '/write', label: 'Write', icon: Sparkles },
  { to: '/notes', label: 'Notes & Search', icon: BookmarkCheck },
  { to: '/agent/calls', label: 'Agent Calls', icon: PhoneCall },
  { to: '/voice', label: 'Live Voice', icon: Mic },
  { to: '/global-call', label: 'Global Call', icon: Phone },
  { to: '/meetings', label: 'Meetings', icon: Video },
  { to: '/chat', label: 'Chat', icon: MessageSquare },
  { to: '/documents', label: 'Documents', icon: FileText },
  { to: '/history', label: 'History', icon: History },
];

const CUSTOMIZE = [
  { to: '/glossaries', label: 'Glossaries', icon: BookOpen },
  { to: '/translation-memory', label: 'Translation Memory', icon: Files },
  { to: '/style-profiles', label: 'Style Profiles', icon: Gauge },
];

const PLATFORM = [
  { to: '/docs', label: 'Docs & SDKs', icon: BookOpen },
  { to: '/api', label: 'API Keys', icon: KeyRound },
  { to: '/usage', label: 'Usage', icon: Gauge },
  { to: '/billing', label: 'Billing', icon: CreditCard },
  { to: '/team', label: 'Team', icon: Users },
  { to: '/settings', label: 'Settings', icon: SettingsIcon },
];

export default function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const user = useAuth((s) => s.user);
  const org = useAuth((s) => s.organizations[0]?.org);
  const isAdmin = useAuth((s) => s.user?.is_platform_admin);
  const logout = useAuth((s) => s.logout);

  return (
    <div className="flex h-screen overflow-hidden bg-[#F4F6F8] text-neutral-900 font-sans">
      <aside className="hidden w-64 shrink-0 flex-col border-r border-black/[0.08] bg-[#FBFBFD] shadow-sm md:flex"
        aria-label="Main navigation">
        <button className="flex items-center gap-2.5 border-b border-black/[0.06] px-5 py-4 text-left transition-colors hover:bg-black/[0.03]"
          onClick={() => navigate(user ? '/dashboard' : '/')}>
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-[#007AFF] shadow-xs">
            <Logo small />
          </div>
          <div>
            <div className="text-[13px] font-semibold tracking-[-0.015em] text-neutral-950 leading-tight">GlobalTalk <span className="text-[#007AFF]">AI</span></div>
            <div className="text-[9px] font-semibold uppercase tracking-widest text-neutral-400 leading-tight mt-0.5">
              every language
            </div>
          </div>
        </button>
        <nav className="flex-1 space-y-4 overflow-y-auto px-3 py-4 pb-5">
          <NavSection items={NAV} />
          <NavSection title="Customize" items={CUSTOMIZE} />
          <NavSection title="Platform" items={[
            ...PLATFORM,
            ...(isAdmin ? [
              { to: '/admin', label: 'Admin', icon: ShieldCheck },
              { to: '/admin/telephony', label: 'Telephony ops', icon: PhoneIncoming },
            ] : []),
          ]} />
        </nav>
        <div className="border-t border-black/[0.06] p-3">
          {user ? (
            <div className="flex items-center gap-2.5 rounded-2xl border border-black/[0.06] bg-black/[0.02] p-2.5">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#007AFF] text-xs font-bold text-white shadow-xs">
                {(user.name || user.email || '?').slice(0, 1).toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-xs font-semibold text-neutral-900 leading-tight">{user.name || user.email}</div>
                <div className="truncate text-[11px] text-neutral-500 leading-tight mt-0.5">{org?.name ?? '—'}</div>
              </div>
              <button onClick={() => { void logout(); navigate('/'); }}
                className="rounded-lg px-2 py-1 text-xs font-medium text-neutral-500 transition-colors hover:bg-black/[0.04] hover:text-neutral-900"
                aria-label="Sign out">
                Sign out
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <button
                onClick={() => navigate('/login')}
                className="apple-btn-primary w-full"
              >
                Sign In to Save
              </button>
            </div>
          )}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile top bar */}
        <header className="material-bar flex items-center justify-between border-b border-black/[0.06] px-4 py-3 md:hidden">
          <button className="flex items-center gap-2 rounded-lg" onClick={() => navigate('/dashboard')}>
            <Logo small />
            <span className="text-sm font-semibold tracking-tight text-neutral-950">GlobalTalk AI</span>
          </button>
          <select aria-label="Navigate"
            className="rounded-lg border border-black/[0.08] bg-white px-2 py-1 text-sm text-neutral-700 shadow-xs focus:border-[#007AFF] focus:outline-none focus:ring-2 focus:ring-[#007AFF]/20"
            onChange={(e) => navigate(e.target.value)} defaultValue="">
            <option value="" disabled>Menu…</option>
            {[...NAV, ...CUSTOMIZE, ...PLATFORM].map((i) => (
              <option key={i.to} value={i.to}>{i.label}</option>
            ))}
          </select>
        </header>
        <main className="min-w-0 flex-1 overflow-y-auto" id="main-content">
          <ErrorBoundary sectionName="PageOutlet">
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

function NavSection({ title, items }: { title?: string; items: typeof NAV }) {
  return (
    <div>
      {title && (
        <div className="px-3 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-neutral-400">
          {title}
        </div>
      )}
      <ul className="space-y-0.5">
        {items.map(({ to, label, icon: Icon }) => (
          <li key={to}>
            <NavLink to={to}
              className={({ isActive }) => cn(
                'group flex items-center gap-2.5 rounded-xl px-3 py-2 text-[13px] font-medium transition-all duration-150 active:scale-[0.98]',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#007AFF]',
                isActive ? 'bg-[#007AFF] text-white shadow-xs font-semibold' : 'text-neutral-700 hover:bg-black/[0.05] hover:text-neutral-950')}>
              <Icon className={cn('h-4 w-4 shrink-0 transition-colors', 'text-neutral-400 group-hover:text-neutral-700')} aria-hidden="true" />
              {label}
            </NavLink>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Logo({ small }: { small?: boolean }) {
  const s = small ? 20 : 26;
  return (
    <svg width={s} height={s} viewBox="0 0 64 64" aria-hidden="true" className="brightness-0 invert">
      <defs>
        <linearGradient id="app-shell-logo-gradient" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#FFFFFF" />
          <stop offset="1" stopColor="#FFFFFF" />
        </linearGradient>
      </defs>
      <circle cx="32" cy="32" r="28" fill="url(#app-shell-logo-gradient)" opacity="0.9" />
      <path d="M22 34 C 22 24, 42 24, 42 34 C 42 44, 22 44, 22 34 Z" fill="#007AFF" />
    </svg>
  );
}
