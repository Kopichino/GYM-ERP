import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { fetchMe, login } from "../api/auth";
import { Button, Card, ErrorText, Input } from "../components/ui";
import { useAuthStore } from "../store/authStore";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const setAuth = useAuthStore((s) => s.setAuth);
  const navigate = useNavigate();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const access = await login({ username, password });
      useAuthStore.getState().setAccessToken(access);
      const user = await fetchMe();
      setAuth(access, user);
      navigate(user.is_staff ? "/admin" : "/dashboard");
    } catch {
      setError("Invalid username or password.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--color-bg)] px-4">
      <Card className="w-full max-w-sm">
        <h1 className="mb-1 text-xl font-bold text-[var(--color-text)]">Welcome back</h1>
        <p className="mb-6 text-sm text-[var(--color-text-muted)]">Log in to IRONCORE</p>
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <Input placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} required />
          <Input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          <ErrorText>{error}</ErrorText>
          <Button type="submit" disabled={loading} className="mt-2">
            {loading ? "Logging in..." : "Log in"}
          </Button>
        </form>
        <p className="mt-4 text-center text-sm text-[var(--color-text-muted)]">
          No account?{" "}
          <Link to="/signup" className="text-[var(--color-accent)] hover:underline">
            Sign up
          </Link>
        </p>
      </Card>
    </div>
  );
}
