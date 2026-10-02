import React from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Logo } from "../components/Layout";
import { Button, Field, Input } from "../components/ui";
import { SocialAuthButtons } from "../components/auth/SocialAuthButtons";
import { useAuth } from "../stores/auth";
import { ApiError } from "../lib/api";

export default function Login() {
  const { login, user, status } = useAuth();
  const nav = useNavigate();
  const loc = useLocation() as { state?: { from?: string } };
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    if (status === "authed" && user) {
      nav(loc.state?.from ?? "/dashboard", { replace: true });
    }
  }, [user, status, nav, loc.state?.from]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim() || !password) {
      setError("Please enter your email and password.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const timeoutPromise = new Promise((_, reject) =>
        setTimeout(() => reject(new Error("Sign in timed out. Please check your connection.")), 10000)
      );
      await Promise.race([login(email.trim(), password), timeoutPromise]);
      nav(loc.state?.from ?? "/dashboard", { replace: true });
    } catch (err: any) {
      setError(err instanceof ApiError ? err.message : (err?.message || "Login failed. Please check your credentials."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-ink-50 p-6">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-2">
          <Logo className="h-10 w-10" />
          <h1 className="text-xl font-bold text-ink-900">Welcome back</h1>
          <p className="text-sm text-ink-400">Sign in to GlobalTalk AI</p>
        </div>
        <div className="gt-card space-y-4 p-6">
          {/* Google, GitHub & Apple SSO */}
          <SocialAuthButtons prefix="Continue with" disabled={busy} onError={setError} />

          <div className="relative my-4 flex items-center justify-center">
            <div className="w-full border-t border-ink-200" />
            <span className="absolute bg-white px-2.5 text-[11px] font-medium uppercase tracking-wider text-ink-400">
              or continue with email
            </span>
          </div>

          <form onSubmit={onSubmit} className="space-y-4" noValidate autoComplete="off">
            <Field label="Email">
              <Input
                type="email"
                required
                autoComplete="off"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@example.com"
              />
            </Field>
            <Field label="Password">
              <Input
                type="password"
                required
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
              />
            </Field>
            {error && (
              <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
                {error}
              </p>
            )}
            <Button type="submit" className="w-full" loading={busy}>
              Sign in
            </Button>
            <p className="text-center text-xs text-ink-400">
              No account? <Link to="/signup" className="font-medium text-signal-700 hover:underline">Create one</Link>
            </p>
          </form>
        </div>
      </div>
    </div>
  );
}
