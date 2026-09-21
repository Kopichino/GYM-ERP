import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { resetPassword } from "../api/auth";
import AuthLayout from "../components/layout/AuthLayout";
import { Button, ErrorText, Input } from "../components/ui";

const LABEL_CLS =
  "mb-1 block text-xs uppercase tracking-wide text-[var(--color-text-muted)]";

/**
 * Where the link in a reset email lands.
 *
 * The link is single use -- the server derives it from the current password, so
 * it stops working the moment the password changes -- which is why a failure
 * here always offers a fresh link rather than just an error.
 */
export default function ResetPasswordPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const uid = params.get("uid") ?? "";
  const token = params.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const mismatch = confirm.length > 0 && password !== confirm;
  // A link copied without its query string cannot work, and saying so up front
  // beats letting someone type a new password twice only to be refused.
  const incomplete = !uid || !token;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (mismatch) return;
    setError("");
    setLoading(true);
    try {
      await resetPassword({ uid, token, password });
      setDone(true);
    } catch (err) {
      const data = (err as { response?: { data?: { password?: string[]; detail?: string } } })
        .response?.data;
      setError(data?.password?.join(" ") || data?.detail || "Could not reset your password.");
    } finally {
      setLoading(false);
    }
  }

  const footer = (
    <>
      Back to{" "}
      <Link to="/login" className="font-semibold text-[var(--color-accent)] hover:underline">
        Log in
      </Link>
    </>
  );

  if (done) {
    return (
      <AuthLayout variant="login" title="Password changed" subtitle="You can log in with it now." footer={footer}>
        <div className="flex flex-col gap-4 text-sm text-[var(--color-text-muted)]">
          <p>Any other device you were signed in on has been signed out.</p>
          <Button onClick={() => navigate("/login")} className="py-2.5">
            Log in
          </Button>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      variant="login"
      title="Set a new password"
      subtitle="Choose a new password for your account."
      footer={footer}
    >
      {incomplete ? (
        <p className="text-sm text-[var(--color-text-muted)]">
          This link is incomplete. Open it straight from the email, or{" "}
          <Link to="/forgot-password" className="font-semibold text-[var(--color-accent)] hover:underline">
            ask for a new one
          </Link>
          .
        </p>
      ) : (
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <div>
            <label htmlFor="reset-password" className={LABEL_CLS}>
              New password
            </label>
            <Input
              id="reset-password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          <div>
            <label htmlFor="reset-confirm" className={LABEL_CLS}>
              Confirm new password
            </label>
            <Input
              id="reset-confirm"
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
            />
          </div>
          {mismatch && <ErrorText>The two passwords do not match.</ErrorText>}
          <ErrorText>{error}</ErrorText>
          {error && (
            <Link
              to="/forgot-password"
              className="text-sm font-semibold text-[var(--color-accent)] hover:underline"
            >
              Ask for a new link
            </Link>
          )}
          <Button type="submit" disabled={loading || mismatch} className="mt-2 py-2.5">
            {loading ? "Saving..." : "Set new password"}
          </Button>
        </form>
      )}
    </AuthLayout>
  );
}
