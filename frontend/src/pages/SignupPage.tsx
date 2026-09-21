import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { fetchMe, login, signup } from "../api/auth";
import AuthLayout from "../components/layout/AuthLayout";
import MfaSignIn, { type PendingSignIn } from "../components/mfa/MfaSignIn";
import { Button, ErrorText, Input } from "../components/ui";
import { useBranding } from "../hooks/useBranding";
import { useAuthStore } from "../store/authStore";

const LABEL_CLS =
  "mb-1.5 block text-sm uppercase tracking-wide text-[var(--color-text-muted)]";

/**
 * Taller fields and a taller button.
 *
 * `h-` rather than `py-`: the shared field and button classes already set
 * `py-2`, and two padding utilities on one element resolve by their order in
 * the generated stylesheet rather than by which was written last -- so an
 * added `py-3` may simply lose. Nothing sets a height, so this always wins.
 */
const FIELD_CLS = "h-12";

export default function SignupPage() {
  const [form, setForm] = useState({
    username: "",
    email: "",
    password: "",
    first_name: "",
    last_name: "",
    referral_code: "",
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  // A new account meets two-step setup straight after it is created.
  const [pending, setPending] = useState<PendingSignIn | null>(null);
  const setAuth = useAuthStore((s) => s.setAuth);
  const navigate = useNavigate();
  const gymName = useBranding()?.name || "IRONCORE";

  function update(key: keyof typeof form) {
    return (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [key]: e.target.value }));
  }

  async function finish(access: string) {
    useAuthStore.getState().setAccessToken(access);
    const user = await fetchMe();
    setAuth(access, user);
    navigate("/dashboard");
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await signup(form);
      const result = await login({ username: form.username, password: form.password });
      if (result.kind === "session") {
        await finish(result.access);
      } else {
        setForm((f) => ({ ...f, password: "" }));
        setPending(result);
      }
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: Record<string, string[]> } })?.response?.data;
      setError(message ? Object.values(message).flat().join(" ") : "Signup failed.");
    } finally {
      setLoading(false);
    }
  }

  if (pending) {
    // The account exists by now, so starting again means logging in to it.
    return <MfaSignIn pending={pending} onSignedIn={finish} onRestart={() => navigate("/login")} />;
  }

  return (
    <AuthLayout
      variant="signup"
      title="Join the gym"
      subtitle={`Create your ${gymName} account — it takes about a minute.`}
      footer={
        <>
          Already a member?{" "}
          <Link to="/login" className="font-semibold text-[var(--color-accent)] hover:underline">
            Log in
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        {/* `htmlFor`/`id` rather than a wrapping label: the implicit
            association wasn't reaching the accessibility tree, which left the
            fields unnamed to a screen reader once the placeholders went. */}
        <div>
          <label htmlFor="signup-username" className={LABEL_CLS}>
            Username
          </label>
          <Input
            id="signup-username"
            className={FIELD_CLS}
            value={form.username}
            onChange={update("username")}
            autoComplete="username"
            required
          />
        </div>
        <div>
          <label htmlFor="signup-email" className={LABEL_CLS}>
            Email
          </label>
          <Input
            id="signup-email"
            className={FIELD_CLS}
            type="email"
            value={form.email}
            onChange={update("email")}
            autoComplete="email"
            required
          />
        </div>
        <div className="flex gap-4">
          <div className="flex-1">
            <label htmlFor="signup-first" className={LABEL_CLS}>
              First name
            </label>
            <Input
              id="signup-first"
              className={FIELD_CLS}
              value={form.first_name}
              onChange={update("first_name")}
              autoComplete="given-name"
            />
          </div>
          <div className="flex-1">
            <label htmlFor="signup-last" className={LABEL_CLS}>
              Last name
            </label>
            <Input
              id="signup-last"
              className={FIELD_CLS}
              value={form.last_name}
              onChange={update("last_name")}
              autoComplete="family-name"
            />
          </div>
        </div>
        <div>
          <label htmlFor="signup-password" className={LABEL_CLS}>
            Password
          </label>
          <Input
            id="signup-password"
            className={FIELD_CLS}
            type="password"
            value={form.password}
            onChange={update("password")}
            autoComplete="new-password"
            required
          />
        </div>
        <div>
          <label htmlFor="signup-referral" className={LABEL_CLS}>
            Referral code <span className="normal-case">(optional)</span>
          </label>
          <Input
            id="signup-referral"
            className={FIELD_CLS}
            value={form.referral_code}
            onChange={update("referral_code")}
          />
        </div>
        <ErrorText>{error}</ErrorText>
        <Button type="submit" disabled={loading} className="mt-3 h-12">
          {loading ? "Creating account..." : "Create account"}
        </Button>
      </form>
    </AuthLayout>
  );
}
