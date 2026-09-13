import ChangePasswordCard from "../../components/ChangePasswordCard";
import { Card, PageHeader } from "../../components/ui";
import { railColor } from "../../lib/theme";
import { useAuthStore } from "../../store/authStore";

const TERM = "text-xs uppercase tracking-wide text-[var(--color-text-muted)]";

/**
 * A trainer's own account.
 *
 * This used to edit their instructor profile -- the name, bio and photo shown
 * on the public instructors page. Instructor profiles have been removed, so
 * what is left to manage here is the account itself.
 */
export default function TrainerProfilePage() {
  const user = useAuthStore((s) => s.user);
  const name = `${user?.first_name ?? ""} ${user?.last_name ?? ""}`.trim();

  return (
    <div>
      <PageHeader title="My Profile" subtitle="Your account and password." />
      <div className="flex flex-col gap-6">
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
        <ChangePasswordCard />
      </div>
    </div>
  );
}
