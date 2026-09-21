import { railColor } from "../lib/theme";
import { useAuthStore } from "../store/authStore";
import { Card } from "./ui";

const TERM = "text-xs uppercase tracking-wide text-[var(--color-text-muted)]";

/** Who is signed in: name, username and email. Shared by the trainer and admin account pages. */
export default function AccountDetailsCard() {
  const user = useAuthStore((s) => s.user);
  const name = `${user?.first_name ?? ""} ${user?.last_name ?? ""}`.trim();

  return (
    <Card accent={railColor(0)}>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
        Account
      </h2>
      <dl className="grid gap-4 text-sm sm:grid-cols-3">
        <div>
          <dt className={TERM}>Name</dt>
          <dd className="mt-0.5 text-[var(--color-text)]">{name || "Not set"}</dd>
        </div>
        <div>
          <dt className={TERM}>Username</dt>
          <dd className="mt-0.5 text-[var(--color-text)]">{user?.username}</dd>
        </div>
        <div>
          <dt className={TERM}>Email</dt>
          <dd className="mt-0.5 truncate text-[var(--color-text)]">{user?.email}</dd>
        </div>
      </dl>
    </Card>
  );
}
