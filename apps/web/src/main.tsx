import React from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { MotionConfig } from "motion/react";
import "./index.css";
import Layout from "./components/Layout";
import { ToastHost } from "./stores/toast";
import { useAuth } from "./stores/auth";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import Dashboard from "./pages/Dashboard";
import TranslatePage from "./pages/Translate";
import WritePage from "./pages/Write";
import Voice from "./pages/Voice";
import Documents from "./pages/Documents";
import Meetings from "./pages/Meetings";
import MeetingRoom from "./pages/MeetingRoom";
import ChatRooms from "./pages/ChatRooms";
import HistoryPage from "./pages/History";
import Glossaries from "./pages/Glossaries";
import TranslationMemory from "./pages/TranslationMemory";
import StyleProfiles from "./pages/StyleProfiles";
import ApiKeys from "./pages/ApiKeys";
import Usage from "./pages/Usage";
import Billing from "./pages/Billing";
import Team from "./pages/Team";
import SettingsPage from "./pages/Settings";
import Admin from "./pages/Admin";
import AgentCalls from "./pages/AgentCalls";
import JoinCall from "./pages/JoinCall";
import AuthCallback from "./pages/AuthCallback";
import AgentStudio from "./pages/AgentStudio";
import DocsPage from "./pages/DocsPage";
import AppShell from "./components/layout/AppShell";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 15_000 },
  },
});

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, initialized } = useAuth();
  const loc = useLocation();

  if (!initialized) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-50 text-slate-600">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-dl-blue border-t-transparent" />
          <div className="text-sm font-medium">Loading your workspace…</div>
        </div>
      </div>
    );
  }
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  return <>{children}</>;
}

function RootGate() {
  // Real sessions only: an authenticated visitor (cookie bootstrap resolves to
  // authed) goes straight to the workspace; everyone else sees the landing page.
  // No demo auto-login and no client-side fake session.
  const { user, initialized } = useAuth();
  if (initialized && user) return <Navigate to="/dashboard" replace />;
  return <Landing />;
}

export default function App() {
  const refreshMe = useAuth((s) => s.refreshMe);
  React.useEffect(() => {
    void refreshMe();
  }, [refreshMe]);

  return (
    <MotionConfig reducedMotion="user">
      <QueryClientProvider client={queryClient}>
        <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <Routes>
            <Route path="/" element={<RootGate />} />
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<Signup />} />
            {/* OAuth redirect landing: provider code -> server-verified session */}
            <Route path="/auth/callback/:provider" element={<AuthCallback />} />
            {/* Public Call Join Route: Recipient joins directly from their mobile or browser without authentication */}
            <Route path="/join/:roomId" element={<JoinCall />} />
            {/* Full-screen Google Meet style meeting room (accessible to all participants via link, no auth wall) */}
            <Route path="/meeting/:id" element={<MeetingRoom />} />
            {/* Public tool pages — linked from Landing & header; without these they bounced to / */}
            <Route element={<AppShell />}>
              <Route path="/agents" element={<AgentStudio />} />
              <Route path="/agent-studio" element={<AgentStudio />} />
              <Route path="/docs" element={<DocsPage />} />
              <Route path="/api/docs" element={<DocsPage />} />
            </Route>
            <Route element={<RequireAuth><Layout /></RequireAuth>}>
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/translate" element={<TranslatePage />} />
              <Route path="/write" element={<WritePage />} />
              <Route path="/voice" element={<Voice />} />
              <Route path="/documents" element={<Documents />} />
              <Route path="/meetings" element={<Meetings />} />
              <Route path="/chat" element={<ChatRooms />} />
              <Route path="/history" element={<HistoryPage />} />
              <Route path="/glossaries" element={<Glossaries />} />
              <Route path="/translation-memory" element={<TranslationMemory />} />
              <Route path="/style-profiles" element={<StyleProfiles />} />
              <Route path="/api" element={<ApiKeys />} />
              <Route path="/usage" element={<Usage />} />
              <Route path="/billing" element={<Billing />} />
              <Route path="/team" element={<Team />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/admin" element={<Admin />} />
              <Route path="/agent/calls" element={<AgentCalls />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          <ToastHost />
        </BrowserRouter>
      </QueryClientProvider>
    </MotionConfig>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
