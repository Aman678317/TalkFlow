import React from "react";
import { Link, useNavigate } from "react-router-dom";
import { Logo } from "../components/Layout";
import { Button, Field, Input } from "../components/ui";
import { SocialAuthButtons } from "../components/auth/SocialAuthButtons";
import { useAuth } from "../stores/auth";
import { ApiError } from "../lib/api";

export default function Signup() {
  const { signup, user, status } = useAuth();
  const nav = useNavigate();
  const [form, setForm] = React.useState({
    email: "", password: "", full_name: "", organization_name: "",
  });
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  React.useEffect(() => {
    if (status === "authed" && user) {
      nav("/dashboard", { replace: true });
    }
  }, [user, status, nav]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.email.trim() || !form.password) {
      setError("Please fill in your email and password.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await signup(form);
      nav("/dashboard", { replace: true });
    } catch (err: any) {
      setError(err instanceof ApiError ? err.message : (err?.message || "Signup failed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-ink-50 p-6">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-2">
          <Logo className="h-10 w-10" />
          <h1 className="text-xl font-bold text-ink-900">Create your workspace</h1>
          <p className="text-sm text-ink-400">Free plan · no credit card</p>
        </div>
        <div className="gt-card space-y-4 p-6">
          {/* Google, GitHub & Apple SSO */}
          <SocialAuthButtons prefix="Sign up with" disabled={busy} onError={setError} />

          <div className="relative my-4 flex items-center justify-center">
            <div className="w-full border-t border-ink-200" />
            <span className="absolute bg-white px-2.5 text-[11px] font-medium uppercase tracking-wider text-ink-400">
              or continue with email
            </span>
          </div>

          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            <Field label="Full name">
              <Input required autoComplete="name" value={form.full_name} onChange={set("full_name")} />
            </Field>
          <Field label="Work email">
            <Input type="email" required autoComplete="email" value={form.email} onChange={set("email")} />
          </Field>
          <Field label="Organization" hint="Used to create your tenant workspace">
            <Input required value={form.organization_name} onChange={set("organization_name")} />
          </Field>
          <Field label="Password" hint="At least 8 characters, letters and numbers">
            <Input type="password" required minLength={8} autoComplete="new-password"
                   value={form.password} onChange={set("password")} />
          </Field>
          {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">{error}</p>}
          <Button type="submit" className="w-full" loading={busy}>Create account</Button>
          <p className="text-center text-xs text-ink-400">
            Already registered? <Link to="/login" className="font-medium text-signal-700 hover:underline">Sign in</Link>
          </p>
        </form>
      </div>
    </div>
  </div>
);
}
