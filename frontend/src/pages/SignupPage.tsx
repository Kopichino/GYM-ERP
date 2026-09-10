import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { fetchMe, login, signup } from "../api/auth";
import AuthLayout from "../components/layout/AuthLayout";
import { Button, ErrorText, Input } from "../components/ui";
import { useBranding } from "../hooks/useBranding";
import { useAuthStore } from "../store/authStore";

const LABEL_CLS =
  "mb-1 block text-xs uppercase tracking-wide text-[var(--color-text-muted)]";

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
  const setAuth = useAuthStore((s) => s.setAuth);
  const navigate = useNavigate();
  const gymName = useBranding()?.name || "IRONCORE";

  function update(key: keyof typeof form) {
    return (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [key]: e.target.value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await signup(form);
      const access = await login({ username: form.username, password: form.password });
      useAuthStore.getState().setAccessToken(access);
      const user = await fetchMe();
      setAuth(access, user);
      navigate("/dashboard");
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: Record<string, string[]> } })?.response?.data;
      setError(message ? Object.values(message).flat().join(" ") : "Signup failed.");
    } finally {
      setLoading(false);
    }
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
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        {/* `htmlFor`/`id` rather than a wrapping label: the implicit
            association wasn't reaching the accessibility tree, which left the
            fields unnamed to a screen reader once the placeholders went. */}
        <div>
          <label htmlFor="signup-username" className={LABEL_CLS}>
            Username
          </label>
          <Input
            id="signup-username"
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
            type="email"
            value={form.email}
            onChange={update("email")}
            autoComplete="email"
            required
          />
        </div>
        <div className="flex gap-3">
          <div className="flex-1">
            <label htmlFor="signup-first" className={LABEL_CLS}>
              First name
            </label>
            <Input
              id="signup-first"
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
            value={form.referral_code}
            onChange={update("referral_code")}
          />
        </div>
        <ErrorText>{error}</ErrorText>
        <Button type="submit" disabled={loading} className="mt-2 py-2.5">
          {loading ? "Creating account..." : "Create account"}
        </Button>
      </form>
    </AuthLayout>
  );
}
