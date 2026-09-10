import { todayIso } from "../../lib/dates";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchClassSessions } from "../../api/schedule";
import { fetchMyMembers } from "../../api/users";
import { AnimatedNumber, Card, EmptyState, LoadingState, PageHeader } from "../../components/ui";
import { useAuthStore } from "../../store/authStore";
import AtRiskPanel from "../../components/AtRiskPanel";
import MyShiftsPanel from "../../components/MyShiftsPanel";
import { railColor } from "../../lib/theme";

export default function TrainerDashboardPage() {
  const user = useAuthStore((s) => s.user);
  const { data: members, isLoading } = useQuery({
    queryKey: ["trainer", "members"],
    queryFn: fetchMyMembers,
  });
  const { data: classes } = useQuery({
    queryKey: ["trainer", "classes"],
    queryFn: () => fetchClassSessions(true),
  });

  const today = todayIso();
  const upcoming = classes?.filter((c) => c.date >= today) ?? [];
  const activeMembers = members?.filter((m) => m.membership_status === "active").length ?? 0;

  return (
    <div>
      <PageHeader
        title={`Welcome, ${user?.first_name || user?.username || "Trainer"}`}
        subtitle="Your members and classes at a glance."
      />
      <div className="grid gap-6 md:grid-cols-3">
        <Card accent={railColor(0)}>
          <p className="font-display text-4xl text-[var(--color-text)]">
            <AnimatedNumber value={members?.length ?? 0} />
          </p>
          <p className="text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">
            Assigned members
          </p>
        </Card>
        <Card accent={railColor(1)}>
          <p className="font-display text-4xl text-[var(--color-text)]">
            <AnimatedNumber value={activeMembers} />
          </p>
          <p className="text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">
            Active memberships
          </p>
        </Card>
        <Card accent={railColor(2)}>
          <p className="font-display text-4xl text-[var(--color-text)]">
            <AnimatedNumber value={upcoming.length} />
          </p>
          <p className="text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">
            Upcoming classes
          </p>
        </Card>
      </div>

      <div className="mt-6 grid gap-6 md:grid-cols-2">
        <Card accent={railColor(3)}>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            Your members
          </h2>
          {isLoading ? (
            <LoadingState />
          ) : !members?.length ? (
            <EmptyState>No members assigned to you yet.</EmptyState>
          ) : (
            <ul className="flex flex-col gap-2">
              {members.slice(0, 8).map((m) => (
                <li
                  key={m.id}
                  className="flex items-center justify-between border-b border-[var(--color-border)] py-2 text-sm last:border-none"
                >
                  <Link
                    to={`/trainer/members/${m.id}`}
                    className="text-[var(--color-text)] hover:text-[var(--color-accent)]"
                  >
                    {`${m.first_name} ${m.last_name}`.trim() || m.username}
                  </Link>
                  <span className="capitalize text-[var(--color-text-muted)]">
                    {m.membership_status || "-"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card accent={railColor(4)}>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            Next classes
          </h2>
          {!upcoming.length ? (
            <EmptyState>No upcoming classes.</EmptyState>
          ) : (
            <ul className="flex flex-col gap-2">
              {upcoming.slice(0, 8).map((c) => (
                <li
                  key={c.id}
                  className="flex items-center justify-between border-b border-[var(--color-border)] py-2 text-sm last:border-none"
                >
                  <span className="text-[var(--color-text)]">{c.title}</span>
                  <span className="text-[var(--color-text-muted)]">
                    {new Date(c.date).toLocaleDateString()} {c.start_time.slice(0, 5)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {/* Scoped to this trainer's own roster by the API, so it is a list they
          can actually act on rather than the whole gym's. */}
      <div className="mt-6 grid gap-6 md:grid-cols-2">
        <AtRiskPanel accent={railColor(5)} />
        <MyShiftsPanel accent={railColor(6)} />
      </div>
    </div>
  );
}
