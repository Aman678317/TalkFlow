import React from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
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
import JoinCall from "./pages/JoinCall";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 15_000 },
  },
});

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, initialized, login } = useAuth();
  const [autoLoggingIn, setAutoLoggingIn] = React.useState(false);
  const loc = useLocation();

  React.useEffect(() => {
    // If not authenticated and not explicitly logged out, seamlessly authenticate as demo user
    // so visitors can use the tools (Translate, Write, Voice, Dashboard, etc.) without bouncing to /login
    if (initialized && !user && typeof window !== "undefined") {
      const explicitlyLoggedOut = localStorage.getItem("gt.logged_out") === "true";
      if (!explicitlyLoggedOut && !autoLoggingIn) {
        setAutoLoggingIn(true);
        login("demo@globaltalk.local", "demo1234")
          .catch((err) => {
            console.warn("Auto demo login error, using guest workspace session:", err);
            const fallbackUser = {
              id: "guest-user",
              email: "demo@globaltalk.local",
              name: "Demo Guest",
              full_name: "Demo Guest",
              is_platform_admin: false,
              email_verified: true,
              default_language: "en",
            };
            const fallbackOrg = {
              id: "guest-org",
              name: "Demo Workspace",
              slug: "demo-workspace",
              plan: "pro",
            };
            try {
              localStorage.setItem("gt.local_user", JSON.stringify(fallbackUser));
              localStorage.setItem("gt.local_org", JSON.stringify(fallbackOrg));
            } catch {}
            useAuth.setState({
              user: fallbackUser,
              org: fallbackOrg,
              organizations: [{ org: fallbackOrg, role: "owner" }],
              role: "owner",
              initialized: true,
              status: "authed",
            });
          })
          .finally(() => {
            setAutoLoggingIn(false);
          });
      }
    }
  }, [initialized, user, autoLoggingIn, login]);

  if (!initialized || autoLoggingIn) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-50 text-slate-600">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-dl-blue border-t-transparent" />
          <div className="text-sm font-medium">Entering GlobalTalk Workspace…</div>
        </div>
      </div>
    );
  }
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  return <>{children}</>;
}

export default function App() {
  const refreshMe = useAuth((s) => s.refreshMe);
  React.useEffect(() => {
    void refreshMe();
  }, [refreshMe]);

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          {/* Public Call Join Route: Recipient joins directly from their mobile or browser without authentication */}
          <Route path="/join/:roomId" element={<JoinCall />} />
          {/* Full-screen Google Meet style meeting room (accessible to all participants via link, no auth wall) */}
          <Route path="/meeting/:id" element={<MeetingRoom />} />
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
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        <ToastHost />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
