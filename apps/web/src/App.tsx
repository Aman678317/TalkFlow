import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { CopilotKit, CopilotSidebar } from '@copilotkit/react-core/v2';
import '@copilotkit/react-core/v2/styles.css';
import { Suspense, lazy } from 'react';
import { useAuth } from './stores/auth';
import ErrorBoundary from './components/common/ErrorBoundary';
import AppShell from './components/layout/AppShell';
import Toaster from './components/layout/Toaster';
import Landing from './pages/Landing';
import Login from './pages/Login';
import Signup from './pages/Signup';

// Route-level code splitting (2026-10-21 reference benchmark).
// The single 841 kB entry chunk shipped every page — including the 561 kB
// meeting/LiveKit bundle — to a visitor who only wanted to translate a
// sentence. Each route now loads on demand; the first paint only carries the
// shell plus the page being opened.
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Translate = lazy(() => import('./pages/Translate'));
const TranslateWebPage = lazy(() => import('./pages/TranslateWebPage'));
const WritePage = lazy(() => import('./pages/Write'));
const NotesPage = lazy(() => import('./pages/Notes'));
const Documents = lazy(() => import('./pages/Documents'));
const Voice = lazy(() => import('./pages/Voice'));
const Meetings = lazy(() => import('./pages/Meetings'));
const MeetingRoom = lazy(() => import('./pages/MeetingRoom'));
const MeetingCompanion = lazy(() => import('./pages/MeetingCompanion'));
const ChatPage = lazy(() => import('./pages/ChatPage'));
const History = lazy(() => import('./pages/History'));
const Glossaries = lazy(() => import('./pages/Glossaries'));
const TranslationMemory = lazy(() => import('./pages/TranslationMemory'));
const StyleProfiles = lazy(() => import('./pages/StyleProfiles'));
const ApiKeysPage = lazy(() => import('./pages/ApiKeys'));
const Usage = lazy(() => import('./pages/Usage'));
const Billing = lazy(() => import('./pages/Billing'));
const Settings = lazy(() => import('./pages/Settings'));
const Team = lazy(() => import('./pages/Team'));
const Admin = lazy(() => import('./pages/Admin'));
const AdminTelephony = lazy(() => import('./pages/AdminTelephony'));
const AgentCalls = lazy(() => import('./pages/AgentCalls'));
const JoinCall = lazy(() => import('./pages/JoinCall'));
const DocsPage = lazy(() => import('./pages/DocsPage'));
const AgentStudio = lazy(() => import('./pages/AgentStudio'));
const AuthCallback = lazy(() => import('./pages/AuthCallback'));

/** Shown while a route chunk is still arriving. */
function RouteFallback() {
  return (
    <div className="flex h-full min-h-[40vh] items-center justify-center" role="status" aria-live="polite">
      <div className="h-8 w-8 animate-spin-slow rounded-full border-2 border-iris-600 border-t-transparent" />
      <span className="sr-only">Loading</span>
    </div>
  );
}

function RootGate() {
  const user = useAuth((s) => s.user);
  const status = useAuth((s) => s.status);
  if (status === 'authed' && user) return <Navigate to="/dashboard" replace />;
  return <Landing />;
}

function RequireAuth({ children }: { children: JSX.Element }) {
  const status = useAuth((s) => s.status);
  const location = useLocation();
  if (status === 'loading') {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-iris-600 border-t-transparent" />
      </div>
    );
  }
  if (status !== 'authed') {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  return children;
}

export default function App() {
  const baseApi = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/+$/, "") || "";
  const runtimeUrl = import.meta.env.VITE_COPILOTKIT_RUNTIME_URL || (baseApi ? `${baseApi}/api/copilotkit` : '/api/copilotkit');
  const publicLicenseKey = import.meta.env.VITE_CPK_INTELLIGENCE_API_KEY || 'cpk-8093_7ThsaDD2_NmHGMwCATGmNJYKt6tcpd5HH';

  return (
    <CopilotKit runtimeUrl={runtimeUrl} publicLicenseKey={publicLicenseKey}>
      <ErrorBoundary sectionName="AppRoot">
        <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route path="/" element={<RootGate />} />
          <Route path="/auth/callback/:provider" element={<AuthCallback />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/meeting/:id" element={<MeetingRoom />} />
          <Route path="/meet-companion" element={<MeetingCompanion />} />
          <Route path="/google-meet" element={<MeetingCompanion />} />
          {/* Public join page — other person opens this link on their phone (NO login required) */}
          <Route path="/join/:roomId" element={<JoinCall />} />
          <Route path="/join" element={<Navigate to="/meetings" replace />} />

          <Route element={<AppShell />}>
            <Route path="/translate" element={<Translate />} />
            <Route path="/translate/page" element={<TranslateWebPage />} />
            <Route path="/write" element={<WritePage />} />
            <Route path="/notes" element={<NotesPage />} />
            <Route path="/agents" element={<AgentStudio />} />
            <Route path="/agent-studio" element={<AgentStudio />} />
            <Route path="/agent" element={<Navigate to="/agents" replace />} />
            <Route path="/docs" element={<DocsPage />} />
            <Route path="/api/docs" element={<DocsPage />} />
            <Route path="/developer" element={<Navigate to="/docs" replace />} />
            <Route path="/developers" element={<Navigate to="/docs" replace />} />
          </Route>

          {/* Protected app shell routes: requires user authentication */}
          <Route element={<RequireAuth><AppShell /></RequireAuth>}>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/documents" element={<Documents />} />
            <Route path="/knowledge" element={<Documents />} />
            <Route path="/knowledge-base" element={<Navigate to="/documents" replace />} />
            <Route path="/voice" element={<Voice />} />
            <Route path="/meetings" element={<Meetings />} />
            <Route path="/meeting" element={<Navigate to="/meetings" replace />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/history" element={<History />} />
            <Route path="/glossaries" element={<Glossaries />} />
            <Route path="/translation-memory" element={<TranslationMemory />} />
            <Route path="/style-profiles" element={<StyleProfiles />} />
            <Route path="/api" element={<ApiKeysPage />} />
            <Route path="/usage" element={<Usage />} />
            <Route path="/billing" element={<Billing />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/team" element={<Team />} />
            <Route path="/admin" element={<Admin />} />
            <Route path="/admin/telephony" element={<AdminTelephony />} />
            <Route path="/agent/calls" element={<AgentCalls />} />
            <Route path="/calls" element={<Navigate to="/agent/calls" replace />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </Suspense>
      </ErrorBoundary>
      <Toaster />
      <CopilotSidebar defaultOpen={false} />
    </CopilotKit>
  );
}
