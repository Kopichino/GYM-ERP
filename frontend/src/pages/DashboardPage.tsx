import { useQuery } from "@tanstack/react-query";
import { fetchCheckInHistory } from "../api/attendance";
import CheckInButton from "../components/CheckInButton";
import { Card, PageHeader } from "../components/ui";
import { useAuthStore } from "../store/authStore";

function formatDuration(checkIn: string, checkOut: string | null) {
  if (!checkOut) return "In progress";
  const ms = new Date(checkOut).getTime() - new Date(checkIn).getTime();
  const minutes = Math.round(ms / 60000);
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

export default function DashboardPage() {
  const user = useAuthStore((s) => s.user);
  const { data: history } = useQuery({ queryKey: ["attendance", "history"], queryFn: fetchCheckInHistory });

  return (
    <div>
      <PageHeader title={`Welcome, ${user?.first_name || user?.username}`} subtitle="Log your visit below." />
      <div className="grid gap-6 md:grid-cols-2">
        <CheckInButton />
        <Card>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            Recent visits
          </h2>
          <ul className="flex flex-col gap-2">
            {history?.slice(0, 8).map((record) => (
              <li
                key={record.id}
                className="flex items-center justify-between border-b border-[var(--color-border)] py-2 text-sm last:border-none"
              >
                <span className="text-[var(--color-text)]">
                  {new Date(record.check_in_time).toLocaleDateString()}
                </span>
                <span className="text-[var(--color-text-muted)]">
                  {formatDuration(record.check_in_time, record.check_out_time)}
                </span>
              </li>
            ))}
            {history?.length === 0 && (
              <p className="text-sm text-[var(--color-text-muted)]">No visits logged yet.</p>
            )}
          </ul>
        </Card>
      </div>
    </div>
  );
}
