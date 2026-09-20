import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { fetchMe, login } from "../api/auth";
import AuthLayout from "../components/layout/AuthLayout";
import MfaSignIn, { type PendingSignIn } from "../components/mfa/MfaSignIn";
import { Button, ErrorText, Input } from "../components/ui";
import { useBranding } from "../hooks/useBranding";
import { homePathFor, useAuthStore } from "../store/authStore";

const LABEL_CLS =
  "mb-1 block text-xs uppercase tracking-wide text-[var(--color-text-muted)]";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  // Set once the password is right and a second step is due.
  const [pending, setPending] = useState<PendingSignIn | null>(null);
  const setAuth = useAuthStore((s) => s.setAuth);
  const navigate = useNavigate();
  const gymName = useBranding()?.name || "IRONCORE";
  const location = useLocation();
  // Set by ProtectedRoute when it bounced someone off a page they asked for
  // -- a scanned check-in QR, most often.
  const from = (location.state as { from?: { pathname: string; search: string } } | null)?.from;

  async function finish(access: string) {
    useAuthStore.getState().setAccessToken(access);
    const user = await fetchMe();
    setAuth(access, user);
    navigate(from ? `${from.pathname}${from.search}` : homePathFor(user));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const result = await login({ username, password });
      if (result.kind === "session") {
        await finish(result.access);
      } else {
        // The password has done its job, and the sign-in token stands in for it
        // from here -- so it is not left sitting in the page.
        setPassword("");
        setPending(result);
      }
    } catch (err) {
      setError(
        (err as { response?: { status?: number } }).response?.status === 429
          ? "Too many attempts. Wait a minute, then try again."
          : "Invalid username or password.",
      );
    } finally {
      setLoading(false);
    }
  }

  if (pending) {
    return (
      <MfaSignIn
        pending={pending}
        onSignedIn={finish}
        onRestart={(message) => {
          setPending(null);
          setError(message ?? "");
        }}
      />
    );
  }

  return (
    <AuthLayout
      variant="login"
      title="Log in"
      subtitle={`Welcome back to ${gymName}.`}
      footer={
        <>
          Not a member yet?{" "}
          <Link to="/signup" className="font-semibold text-[var(--color-accent)] hover:underline">
            Sign up
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        {/* `htmlFor`/`id` rather than a wrapping label: the implicit
            association wasn't reaching the accessibility tree, which left both
            fields unnamed to a screen reader once the placeholders went. */}
        <div>
          <label htmlFor="login-username" className={LABEL_CLS}>
            Username
          </label>
          <Input
            id="login-username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
          />
        </div>
        <div>
          <div className="flex items-baseline justify-between gap-3">
            <label htmlFor="login-password" className={LABEL_CLS}>
              Password
            </label>
            <Link
              to="/forgot-password"
              className="text-xs font-semibold text-[var(--color-accent)] hover:underline"
            >
              Forgot password?
            </Link>
          </div>
          <Input
            id="login-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </div>
        <ErrorText>{error}</ErrorText>
        <Button type="submit" disabled={loading} className="mt-2 py-2.5">
          {loading ? "Logging in..." : "Sign in"}
        </Button>
      </form>
    </AuthLayout>
  );
}
