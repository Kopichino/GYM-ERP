import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { changePassword } from "../api/auth";
import { statusColor } from "../lib/theme";
import { useAuthStore } from "../store/authStore";
import { Button, Card, ErrorText, Input } from "./ui";

const LABEL = "mb-1 block text-xs uppercase tracking-wide text-[var(--color-text-muted)]";

type ChangeError = {
  response?: {
    data?: { current_password?: string[]; new_password?: string[]; detail?: string };
    status?: number;
  };
};

/**
 * Change your own password while signed in.
 *
 * Asks for the current one first. Changing a password is the one thing a stolen
 * session should not be able to do quietly, because it locks the real owner out.
 * On success the server ends every other session, and this one is handed a fresh
 * token -- so changing a password does not also log you out of the page you did
 * it on.
 */
export default function ChangePasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  // Only flagged once they have started typing the confirmation, so the card
  // does not open on an error about a field nobody has touched.
  const mismatch = confirm.length > 0 && next !== confirm;

  const save = useMutation({
    mutationFn: () => changePassword({ current_password: current, new_password: next }),
    onSuccess: (access) => {
      useAuthStore.getState().setAccessToken(access);
      setCurrent("");
      setNext("");
      setConfirm("");
      setError("");
      setDone(true);
    },
    onError: (err: ChangeError) => {
      const data = err.response?.data;
      setDone(false);
      setError(
        err.response?.status === 429
          ? "Too many attempts. Wait a minute and try again."
          : data?.current_password?.join(" ") ||
              data?.new_password?.join(" ") ||
              data?.detail ||
              "Could not change your password.",
      );
    },
  });

  return (
    <Card accent={statusColor("neutral")}>
      <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
        Change password
      </h2>
      <p className="mb-4 max-w-prose text-sm text-[var(--color-text-muted)]">
        Any other device you are signed in on will be signed out.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (mismatch) return;
          setDone(false);
          save.mutate();
        }}
        className="grid max-w-md gap-3"
      >
        <div>
          <label htmlFor="pw-current" className={LABEL}>
            Current password
          </label>
          <Input
            id="pw-current"
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            required
          />
        </div>
        <div>
          <label htmlFor="pw-new" className={LABEL}>
            New password
          </label>
          <Input
            id="pw-new"
            type="password"
            autoComplete="new-password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            required
          />
        </div>
        <div>
          <label htmlFor="pw-confirm" className={LABEL}>
            Confirm new password
          </label>
          <Input
            id="pw-confirm"
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
          />
        </div>
        {mismatch && <ErrorText>The two new passwords do not match.</ErrorText>}
        <ErrorText>{error}</ErrorText>
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" disabled={save.isPending || !current || !next || mismatch}>
            {save.isPending ? "Saving..." : "Change password"}
          </Button>
          {done && (
            <span className="text-sm" style={{ color: statusColor("positive") }}>
              Password changed.
            </span>
          )}
        </div>
      </form>
    </Card>
  );
}
