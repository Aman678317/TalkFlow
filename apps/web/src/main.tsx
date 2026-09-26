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
      <div className="flex h-full items-center justify-center text-ink-400">
        <div className="animate-pulse text-sm">Loading GlobalTalk…</div>
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
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route element={<RequireAuth><Layout /></RequireAuth>}>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/translate" element={<TranslatePage />} />
            <Route path="/documents" element={<Documents />} />
            <Route path="/meetings" element={<Meetings />} />
            <Route path="/meeting/:id" element={<MeetingRoom />} />
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
