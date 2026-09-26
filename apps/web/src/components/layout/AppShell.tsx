import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import {
  BookOpen, CreditCard, FileText, Files, Gauge, History, KeyRound, Languages,
  LayoutDashboard, Mic, MessageSquare, Phone, Settings as SettingsIcon,
  ShieldCheck, Sparkles, Users, Video,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '@/stores/auth';

const NAV = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/translate', label: 'Translate', icon: Languages },
  { to: '/write', label: 'Write', icon: Sparkles },
  { to: '/voice', label: 'Live Voice', icon: Mic },
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
  { to: '/api', label: 'API Keys', icon: KeyRound },
  { to: '/usage', label: 'Usage', icon: Gauge },
  { to: '/billing', label: 'Billing', icon: CreditCard },
  { to: '/team', label: 'Team', icon: Users },
  { to: '/settings', label: 'Settings', icon: SettingsIcon },
];

export default function AppShell() {
  const navigate = useNavigate();
  const user = useAuth((s) => s.user);
  const org = useAuth((s) => s.organizations[0]?.org);
  const isAdmin = useAuth((s) => s.user?.is_platform_admin);
  const logout = useAuth((s) => s.logout);

  return (
    <div className="flex h-screen overflow-hidden">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-slate-200 bg-white md:flex"
             aria-label="Main navigation">
        <button className="flex items-center gap-2.5 px-5 py-5 text-left"
                onClick={() => navigate('/dashboard')}>
          <Logo />
          <div>
            <div className="text-sm font-bold tracking-tight text-slate-900">GlobalTalk AI</div>
            <div className="text-[10px] font-medium uppercase tracking-widest text-lagoon-600">
              one conversation · every language
            </div>
          </div>
        </button>
        <nav className="flex-1 space-y-4 overflow-y-auto px-3 pb-4">
          <NavSection items={NAV} />
          <NavSection title="Customize" items={CUSTOMIZE} />
          <NavSection title="Platform" items={[
            ...PLATFORM,
            ...(isAdmin ? [{ to: '/admin', label: 'Admin', icon: ShieldCheck }] : []),
          ]} />
        </nav>
        <div className="border-t border-slate-100 px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-iris-100 text-sm font-bold text-iris-700">
              {(user?.name || user?.email || '?').slice(0, 1).toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium text-slate-800">{user?.name || user?.email}</div>
              <div className="truncate text-xs text-slate-500">{org?.name ?? '—'}</div>
            </div>
            <button onClick={() => { void logout(); navigate('/'); }}
                    className="text-xs font-medium text-slate-400 hover:text-rose-600"
                    aria-label="Sign out">
              Sign out
            </button>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile top bar */}
        <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3 md:hidden">
          <button className="flex items-center gap-2" onClick={() => navigate('/dashboard')}>
            <Logo small />
            <span className="text-sm font-bold">GlobalTalk AI</span>
          </button>
          <select aria-label="Navigate"
                  className="rounded-lg border border-slate-300 px-2 py-1 text-sm"
                  onChange={(e) => navigate(e.target.value)} defaultValue="">
            <option value="" disabled>Menu…</option>
            {[...NAV, ...CUSTOMIZE, ...PLATFORM].map((i) => (
              <option key={i.to} value={i.to}>{i.label}</option>
            ))}
          </select>
        </header>
        <main className="min-w-0 flex-1 overflow-y-auto" id="main-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function NavSection({ title, items }: { title?: string; items: typeof NAV }) {
  return (
    <div>
      {title && (
        <div className="px-3 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-widest text-slate-400">
          {title}
        </div>
      )}
      <ul className="space-y-0.5">
        {items.map(({ to, label, icon: Icon }) => (
          <li key={to}>
            <NavLink to={to}
              className={({ isActive }) => cn(
                'flex items-center gap-3 rounded-xl2 px-3 py-2 text-sm font-medium transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-iris-500',
                isActive ? 'bg-iris-50 text-iris-700' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900')}>
              <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
              {label}
            </NavLink>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Logo({ small }: { small?: boolean }) {
  const s = small ? 26 : 32;
  return (
    <svg width={s} height={s} viewBox="0 0 64 64" aria-hidden="true">
      <defs>
        <linearGradient id="gt-logo" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#6d5fe6" />
          <stop offset="1" stopColor="#06c3b3" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="14" fill="url(#gt-logo)" />
      <g fill="none" stroke="#fff" strokeWidth="4.2" strokeLinecap="round">
        <path d="M20 22c-4 4-4 16 0 20" />
        <path d="M44 22c4 4 4 16 0 20" />
        <circle cx="32" cy="32" r="8.5" />
      </g>
      <circle cx="32" cy="32" r="3" fill="#fff" />
    </svg>
  );
}

export { Phone };
