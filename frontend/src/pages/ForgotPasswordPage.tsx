import { useState } from "react";
import { Link } from "react-router-dom";
import { requestPasswordReset } from "../api/auth";
import AuthLayout from "../components/layout/AuthLayout";
import { Button, ErrorText, Input } from "../components/ui";

const LABEL_CLS =
  "mb-1 block text-xs uppercase tracking-wide text-[var(--color-text-muted)]";

/**
 * Asking for a reset link.
 *
 * The answer is the same whether or not the address has an account -- saying
 * otherwise would turn this page into a way to find out who is a member. It is
 * also how an imported member, created without a password, sets their first one.
 */
export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await requestPasswordReset(email);
      setSent(true);
    } catch (err) {
      const status = (err as { response?: { status?: number } }).response?.status;
      setError(
        status === 429
          ? "Too many requests from here. Please wait a while and try again."
          : "Could not send that just now. Please try again.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout
      variant="login"
      title="Forgot password"
      subtitle="We will email you a link to choose a new one."
      footer={
        <>
          Remembered it?{" "}
          <Link to="/login" className="font-semibold text-[var(--color-accent)] hover:underline">
            Log in
          </Link>
        </>
      }
    >
      {sent ? (
        <div className="flex flex-col gap-3 text-sm text-[var(--color-text-muted)]">
          <p className="text-base font-semibold text-[var(--color-text)]">Check your inbox.</p>
          <p>
            If <b className="text-[var(--color-text)]">{email}</b> has an account, a link to reset
            the password is on its way. It works once, within the next 24 hours.
          </p>
          <p>Nothing arrived? Check your spam folder, or ask the front desk to set one for you.</p>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <div>
            <label htmlFor="forgot-email" className={LABEL_CLS}>
              Email
            </label>
            <Input
              id="forgot-email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <ErrorText>{error}</ErrorText>
          <Button type="submit" disabled={loading} className="mt-2 py-2.5">
            {loading ? "Sending..." : "Send reset link"}
          </Button>
        </form>
      )}
    </AuthLayout>
  );
}
