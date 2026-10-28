import React from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { MotionConfig } from "motion/react";
import "./index.css";
import { ToastHost } from "./stores/toast";
import { useAuth } from "./stores/auth";
import App from "./App";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 15_000 },
  },
});

export default function Root() {
  const refreshMe = useAuth((s) => s.refreshMe);
  React.useEffect(() => {
    void refreshMe();
  }, [refreshMe]);

  return (
    <MotionConfig reducedMotion="user">
      <QueryClientProvider client={queryClient}>
        <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <App />
          <ToastHost />
        </BrowserRouter>
      </QueryClientProvider>
    </MotionConfig>
  );
}

createRoot(document.getElementById("root")!).render(<Root />);
