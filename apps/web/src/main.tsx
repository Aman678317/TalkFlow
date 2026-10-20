import React from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { MotionConfig } from "motion/react";
import { Suspense, lazy } from "react";
import "./index.css";
import Layout from "./components/Layout";
import { ToastHost } from "./stores/toast";
import { useAuth } from "./stores/auth";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import AppShell from "./components/layout/AppShell";

// Route-level code splitting (2026-10-21 reference benchmark).
// This entry shipped every page — including the ~560 kB meeting/LiveKit
// bundle — to a visitor who only wanted to translate a sentence. Each route
// now loads on demand, so the first paint carries the shell plus the page
// being opened. Landing/Login/Signup stay eager: they are the first paint.
const Dashboard = lazy(() => import("./pages/Dashboard"));
const TranslatePage = lazy(() => import("./pages/Translate"));
const WritePage = lazy(() => import("./pages/Write"));
const Voice = lazy(() => import("./pages/Voice"));
const Documents = lazy(() => import("./pages/Documents"));
const Meetings = lazy(() => import("./pages/Meetings"));
const MeetingRoom = lazy(() => import("./pages/MeetingRoom"));
const ChatRooms = lazy(() => import("./pages/ChatRooms"));
const HistoryPage = lazy(() => import("./pages/History"));
const Glossaries = lazy(() => import("./pages/Glossaries"));
const TranslationMemory = lazy(() => import("./pages/TranslationMemory"));
const StyleProfiles = lazy(() => import("./pages/StyleProfiles"));
const ApiKeys = lazy(() => import("./pages/ApiKeys"));
const Usage = lazy(() => import("./pages/Usage"));
const Billing = lazy(() => import("./pages/Billing"));
const Team = lazy(() => import("./pages/Team"));
const SettingsPage = lazy(() => import("./pages/Settings"));
const Admin = lazy(() => import("./pages/Admin"));
const AdminTelephony = lazy(() => import("./pages/AdminTelephony"));
const AgentCalls = lazy(() => import("./pages/AgentCalls"));
const JoinCall = lazy(() => import("./pages/JoinCall"));
const AuthCallback = lazy(() => import("./pages/AuthCallback"));
const AgentStudio = lazy(() => import("./pages/AgentStudio"));
const DocsPage = lazy(() => import("./pages/DocsPage"));

/** Shown while a route chunk is still arriving. */
function RouteFallback() {
  return (
    <div className="flex h-full min-h-[40vh] items-center justify-center" role="status" aria-live="polite">
      <div className="h-8 w-8 animate-spin-slow rounded-full border-2 border-iris-600 border-t-transparent" />
      <span className="sr-only">Loading</span>
    </div>
  );
}

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
          <Suspense fallback={<RouteFallback />}>
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
              <Route path="/admin/telephony" element={<AdminTelephony />} />
              <Route path="/agent/calls" element={<AgentCalls />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          </Suspense>
          <ToastHost />
        </BrowserRouter>
      </QueryClientProvider>
    </MotionConfig>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
