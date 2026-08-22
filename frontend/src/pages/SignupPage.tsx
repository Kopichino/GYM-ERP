import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { fetchMe, login, signup } from "../api/auth";
import { Button, Card, ErrorText, Input } from "../components/ui";
import { useAuthStore } from "../store/authStore";

export default function SignupPage() {
  const [form, setForm] = useState({ username: "", email: "", password: "", first_name: "", last_name: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const setAuth = useAuthStore((s) => s.setAuth);
  const navigate = useNavigate();

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
    <div className="flex min-h-screen items-center justify-center bg-[var(--color-bg)] px-4 py-8">
      <Card className="w-full max-w-sm">
        <h1 className="mb-1 text-xl font-bold text-[var(--color-text)]">Join the gym</h1>
        <p className="mb-6 text-sm text-[var(--color-text-muted)]">Create your IRONCORE account</p>
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <Input placeholder="Username" value={form.username} onChange={update("username")} required />
          <Input type="email" placeholder="Email" value={form.email} onChange={update("email")} required />
          <div className="flex gap-3">
            <Input placeholder="First name" value={form.first_name} onChange={update("first_name")} />
            <Input placeholder="Last name" value={form.last_name} onChange={update("last_name")} />
          </div>
          <Input
            type="password"
            placeholder="Password"
            value={form.password}
            onChange={update("password")}
            required
          />
          <ErrorText>{error}</ErrorText>
          <Button type="submit" disabled={loading} className="mt-2">
            {loading ? "Creating account..." : "Sign up"}
          </Button>
        </form>
        <p className="mt-4 text-center text-sm text-[var(--color-text-muted)]">
          Already a member?{" "}
          <Link to="/login" className="text-[var(--color-accent)] hover:underline">
            Log in
          </Link>
        </p>
      </Card>
    </div>
  );
}
