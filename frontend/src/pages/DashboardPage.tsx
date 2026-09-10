import { useQuery } from "@tanstack/react-query";
import { fetchCheckInHistory } from "../api/attendance";
import BodyStatsTile from "../components/BodyStatsTile";
import CheckInButton from "../components/CheckInButton";
import ConsistencyCalendar from "../components/ConsistencyCalendar";
import FeedbackPrompt from "../components/FeedbackPrompt";
import PRCelebration from "../components/PRCelebration";
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
      {/* Recent visits sits under the calendar rather than under the check-in
          card: the left column is much the taller of the two, so putting the
          visit list there left the right column empty and the page long. The
          two also belong together -- both answer "how often am I coming in?". */}
      {/* Above the columns: a PR is the best thing that can be on this
          page, and it renders nothing at all when there is not one. */}
      <div className="mb-6 empty:mb-0">
        <PRCelebration />
      </div>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <div className="flex flex-col gap-6">
          <CheckInButton />
          {/* Renders nothing unless a survey is actually pending, so it
              never takes up space for a member with nothing to answer. */}
          <FeedbackPrompt />
          <BodyStatsTile />
        </div>
        <div className="flex flex-col gap-6">
          <ConsistencyCalendar />
          <Card accent={"#4f8dfd"}>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              Recent visits
            </h2>
            {/* Two columns of dates on anything but a phone: eight one-line
                rows stacked is a lot of height for very little information. */}
            <ul className="grid gap-x-6 sm:grid-cols-2">
              {history?.slice(0, 8).map((record) => (
                <li
                  key={record.id}
                  className="flex items-center justify-between border-b border-[var(--color-border)] py-2 text-sm last:border-none sm:[&:nth-last-child(2)]:border-none"
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
    </div>
  );
}
