import React from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../../stores/auth";
import { useToasts } from "../../stores/toasts";
import { ApiError } from "../../lib/api";
import { Spinner } from "../ui";

export function GoogleIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.82-2.4 3.68v3.05h3.88c2.27-2.09 3.66-5.17 3.66-9.17z"
      />
      <path
        fill="#34A853"
        d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.25v3.15C3.26 21.36 7.33 24 12 24z"
      />
      <path
        fill="#FBBC05"
        d="M5.28 14.27c-.25-.72-.38-1.49-.38-2.27s.13-1.55.38-2.27V6.58H1.25C.45 8.16 0 9.94 0 12s.45 3.84 1.25 5.42l4.03-3.15z"
      />
      <path
        fill="#EA4335"
        d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.33 0 3.26 2.64 1.25 6.58l4.03 3.15c.95-2.83 3.6-4.98 6.72-4.98z"
      />
    </svg>
  );
}

export function GitHubIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
      />
    </svg>
  );
}

export function AppleIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.81-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M15.97 6.37c.62-.75 1.04-1.8 0.93-2.85-.9.04-2 .6-2.65 1.35-.58.67-1.09 1.74-.96 2.77 1.01.08 2.05-.52 2.68-1.27z" />
    </svg>
  );
}

export interface SocialAuthButtonsProps {
  prefix?: "Continue with" | "Sign in with" | "Sign up with";
  layout?: "stacked" | "grid";
  disabled?: boolean;
  onSuccess?: () => void;
  onError?: (msg: string) => void;
}

export function SocialAuthButtons({
  prefix = "Continue with",
  layout = "stacked",
  disabled = false,
  onSuccess,
  onError,
}: SocialAuthButtonsProps) {
  const socialLogin = useAuth((s) => s.socialLogin);
  const pushToast = useToasts((s) => s.push);
  const nav = useNavigate();
  const loc = useLocation() as { state?: { from?: string } };
  const [activeProvider, setActiveProvider] = React.useState<"google" | "github" | "apple" | null>(null);
  const [customModal, setCustomModal] = React.useState<"google" | "github" | "apple" | null>(null);
  const [customEmail, setCustomEmail] = React.useState("");
  const [customName, setCustomName] = React.useState("");

  async function handleProviderLogin(
    provider: "google" | "github" | "apple",
    details?: { email?: string; name?: string }
  ) {
    if (disabled || activeProvider) return;
    setActiveProvider(provider);
    try {
      const timeoutPromise = new Promise((_, reject) =>
        setTimeout(() => reject(new Error("Social sign in timed out. Please check your connection.")), 10000)
      );
      await Promise.race([socialLogin(provider, details), timeoutPromise]);
      const providerLabel = provider === "google" ? "Google" : provider === "github" ? "GitHub" : "Apple";
      pushToast("success", `Signed in with ${providerLabel}`, "Welcome to GlobalTalk AI");
      if (onSuccess) {
        onSuccess();
      } else {
        nav(loc.state?.from ?? "/dashboard", { replace: true });
      }
    } catch (err: any) {
      const msg = err instanceof ApiError ? err.message : (err?.message || `Failed to sign in with ${provider}`);
      if (onError) onError(msg);
      pushToast("error", "Authentication error", msg);
    } finally {
      setActiveProvider(null);
      setCustomModal(null);
    }
  }

  const providers = [
    {
      id: "google" as const,
      name: "Google",
      icon: <GoogleIcon className="h-4 w-4 shrink-0" />,
      buttonClass:
        "border-slate-200 bg-white text-slate-700 hover:bg-slate-50 hover:border-slate-300 focus-visible:ring-blue-500",
    },
    {
      id: "github" as const,
      name: "GitHub",
      icon: <GitHubIcon className="h-4 w-4 shrink-0 text-slate-900" />,
      buttonClass:
        "border-slate-200 bg-white text-slate-800 hover:bg-slate-50 hover:border-slate-300 focus-visible:ring-slate-700",
    },
    {
      id: "apple" as const,
      name: "Apple",
      icon: <AppleIcon className="h-4 w-4 shrink-0 text-slate-950" />,
      buttonClass:
        "border-slate-200 bg-white text-slate-900 hover:bg-slate-50 hover:border-slate-300 focus-visible:ring-black",
    },
  ];

  if (layout === "grid") {
    return (
      <div className="space-y-2">
        <div className="grid grid-cols-3 gap-2.5">
          {providers.map((p) => {
            const isLoading = activeProvider === p.id;
            return (
              <button
                key={p.id}
                type="button"
                disabled={disabled || activeProvider !== null}
                onClick={() => handleProviderLogin(p.id)}
                className={`relative flex h-10 items-center justify-center gap-2 rounded-xl border px-3 text-xs font-semibold shadow-xs transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 ${p.buttonClass}`}
                title={`${prefix} ${p.name}`}
                aria-label={`${prefix} ${p.name}`}
              >
                {isLoading ? <Spinner className="h-3.5 w-3.5" /> : p.icon}
                <span className="truncate">{p.name}</span>
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2.5">
      {providers.map((p) => {
        const isLoading = activeProvider === p.id;
        return (
          <button
            key={p.id}
            type="button"
            disabled={disabled || activeProvider !== null}
            onClick={() => handleProviderLogin(p.id)}
            className={`relative flex h-10 w-full items-center justify-center gap-3 rounded-xl border px-4 text-sm font-medium shadow-xs transition active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 ${p.buttonClass}`}
            aria-label={`${prefix} ${p.name}`}
          >
            {isLoading ? <Spinner className="h-4 w-4 text-slate-600" /> : p.icon}
            <span className="text-slate-700">
              {prefix} {p.name}
            </span>
          </button>
        );
      })}

      {/* Optional custom identity prompt for advanced testing */}
      {customModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-xs">
          <div className="w-full max-w-sm rounded-2xl bg-white p-5 shadow-xl animate-in fade-in zoom-in-95">
            <h3 className="text-base font-semibold text-slate-900">
              Sign in with custom {customModal.toUpperCase()}
            </h3>
            <p className="mt-1 text-xs text-slate-500">
              Specify your account email to link or sign in as this social user.
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleProviderLogin(customModal, {
                  email: customEmail || undefined,
                  name: customName || undefined,
                });
              }}
              className="mt-4 space-y-3"
            >
              <div>
                <label className="text-xs font-medium text-slate-700">Email</label>
                <input
                  type="email"
                  required
                  value={customEmail}
                  onChange={(e) => setCustomEmail(e.target.value)}
                  placeholder={`user@${customModal === "google" ? "gmail.com" : customModal === "github" ? "github.com" : "icloud.com"}`}
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-1.5 text-sm"
                />
              </div>
              <div>
                <label className="text-xs font-medium text-slate-700">Full Name (optional)</label>
                <input
                  type="text"
                  value={customName}
                  onChange={(e) => setCustomName(e.target.value)}
                  placeholder="e.g. Alex Morgan"
                  className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-1.5 text-sm"
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setCustomModal(null)}
                  className="rounded-lg px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="rounded-lg bg-iris-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-iris-700"
                >
                  Continue
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
