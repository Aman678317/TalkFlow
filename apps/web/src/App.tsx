import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { CopilotKit, CopilotSidebar } from '@copilotkit/react-core/v2';
import '@copilotkit/react-core/v2/styles.css';
import { useAuth } from './stores/auth';
import ErrorBoundary from './components/common/ErrorBoundary';
import AppShell from './components/layout/AppShell';
import Toaster from './components/layout/Toaster';
import Landing from './pages/Landing';
import Login from './pages/Login';
import Signup from './pages/Signup';
import Dashboard from './pages/Dashboard';
import Translate from './pages/Translate';
import WritePage from './pages/Write';
import Documents from './pages/Documents';
import Voice from './pages/Voice';
import Meetings from './pages/Meetings';
import MeetingRoom from './pages/MeetingRoom';
import ChatPage from './pages/ChatPage';
import History from './pages/History';
import Glossaries from './pages/Glossaries';
import TranslationMemory from './pages/TranslationMemory';
import StyleProfiles from './pages/StyleProfiles';
import ApiKeysPage from './pages/ApiKeys';
import Usage from './pages/Usage';
import Billing from './pages/Billing';
import Settings from './pages/Settings';
import Team from './pages/Team';
import Admin from './pages/Admin';
import JoinCall from './pages/JoinCall';
import DocsPage from './pages/DocsPage';

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
  const runtimeUrl = import.meta.env.VITE_COPILOTKIT_RUNTIME_URL || '/api/copilotkit';
  const publicLicenseKey = import.meta.env.VITE_CPK_INTELLIGENCE_API_KEY || 'cpk-8093_7ThsaDD2_NmHGMwCATGmNJYKt6tcpd5HH';

  return (
    <CopilotKit runtimeUrl={runtimeUrl} publicLicenseKey={publicLicenseKey}>
      <ErrorBoundary sectionName="AppRoot">
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/meeting/:id" element={<MeetingRoom />} />
          {/* Public join page — other person opens this link on their phone (NO login required) */}
          <Route path="/join/:roomId" element={<JoinCall />} />

          <Route element={<AppShell />}>
            <Route path="/translate" element={<Translate />} />
            <Route path="/write" element={<WritePage />} />
            <Route path="/docs" element={<DocsPage />} />
            <Route path="/api/docs" element={<DocsPage />} />
          </Route>

          {/* Protected app shell routes: requires user authentication */}
          <Route element={<RequireAuth><AppShell /></RequireAuth>}>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/documents" element={<Documents />} />
            <Route path="/voice" element={<Voice />} />
            <Route path="/meetings" element={<Meetings />} />
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
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </ErrorBoundary>
      <Toaster />
      <CopilotSidebar defaultOpen={false} />
    </CopilotKit>
  );
}
