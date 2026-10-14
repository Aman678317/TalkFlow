import React from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Logo } from "../components/Layout";
import { useAuth } from "../stores/auth";
import { friendlyMessage } from "../lib/api";

/**
 * OAuth redirect landing (GitHub today). Exchanges the provider authorization code
 * for a server-verified session. The `state` parameter is checked against the value
 * stashed before the redirect (CSRF defence for the code flow).
 */
export default function AuthCallback() {
  const { provider } = useParams();
  const [params] = useSearchParams();
  const nav = useNavigate();
  const socialLogin = useAuth((s) => s.socialLogin);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    if (provider !== "github") {
      setError("Unsupported sign-in provider.");
      return;
    }
    const err = params.get("error");
    if (err) {
      setError(`Sign-in was not completed: ${params.get("error_description") || err}`);
      return;
    }
    const code = params.get("code");
    const state = params.get("state");
    let expected: string | null = null;
    try {
      expected = sessionStorage.getItem("gt.oauth.state");
      sessionStorage.removeItem("gt.oauth.state");
    } catch { /* storage unavailable */ }
    if (!code) {
      setError("Sign-in was cancelled or returned no authorization code.");
      return;
    }
    if (!state || !expected || state !== expected) {
      setError("Sign-in state mismatch — please try again.");
      return;
    }
    socialLogin("github", { code })
      .then(() => nav("/dashboard", { replace: true }))
      .catch((e) => setError(friendlyMessage(e)));
  }, [provider, params, nav, socialLogin]);

  return (
    <div className="flex min-h-full items-center justify-center bg-ink-50 p-6">
      <div className="w-full max-w-sm gt-card space-y-4 p-6 text-center">
        <div className="mb-2 flex flex-col items-center gap-2">
          <Logo className="h-10 w-10" />
          <h1 className="text-lg font-bold tracking-title text-ink-900">Completing sign-in…</h1>
        </div>
        {error ? (
          <>
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
              {error}
            </p>
            <Link to="/login" className="text-sm font-medium text-signal-700 hover:underline">
              Back to sign in
            </Link>
          </>
        ) : (
          <p className="text-sm text-ink-400">Verifying your {provider === "github" ? "GitHub" : provider} identity with the server.</p>
        )}
      </div>
    </div>
  );
}
