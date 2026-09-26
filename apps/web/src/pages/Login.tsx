import React from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Logo } from "../components/Layout";
import { Button, Field, Input } from "../components/ui";
import { useAuth } from "../stores/auth";
import { ApiError } from "../lib/api";

export default function Login() {
  const login = useAuth((s) => s.login);
  const nav = useNavigate();
  const loc = useLocation() as { state?: { from?: string } };
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(email, password);
      nav(loc.state?.from ?? "/dashboard", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed");
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
        <form onSubmit={onSubmit} className="gt-card space-y-4 p-6" noValidate>
          <Field label="Email">
            <Input type="email" required autoComplete="email" value={email}
                   onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />
          </Field>
          <Field label="Password">
            <Input type="password" required autoComplete="current-password" value={password}
                   onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />
          </Field>
          {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">{error}</p>}
          <Button type="submit" className="w-full" loading={busy}>Sign in</Button>
          <p className="text-center text-xs text-ink-400">
            No account? <Link to="/signup" className="font-medium text-signal-700 hover:underline">Create one</Link>
          </p>
        </form>
        <p className="mt-6 text-center text-[11px] text-ink-400">
          Local dev account: <code className="rounded bg-ink-100 px-1">admin@globaltalk.dev</code> /{" "}
          <code className="rounded bg-ink-100 px-1">Demo1234!</code>
        </p>
      </div>
    </div>
  );
}
