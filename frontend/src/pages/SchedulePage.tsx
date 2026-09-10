import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useState } from "react";
import {
  bookClass,
  cancelBooking,
  fetchClassSessions,
  fetchMyBookings,
  type ClassSession,
} from "../api/schedule";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  ErrorText,
  LoadingState,
  PageHeader,
} from "../components/ui";
import { fadeUp, staggerContainer } from "../lib/motion";
import { useAuthStore } from "../store/authStore";
import { railColor } from "../lib/theme";

const dayLabel = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });

function SeatCount({ session }: { session: ClassSession }) {
  if (session.capacity === null) {
    return <p className="text-xs text-[var(--color-text-muted)]">{session.booked_count} booked</p>;
  }
  const left = session.spots_left ?? 0;
  return (
    <p className="text-xs" style={{ color: left === 0 ? "var(--color-accent-2)" : "var(--color-text-muted)" }}>
      {left === 0 ? "Full" : `${left} of ${session.capacity} left`}
    </p>
  );
}

export default function SchedulePage() {
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const canBook = user?.role === "member";
  const [error, setError] = useState("");

  const { data: sessions, isLoading, isError } = useQuery({
    queryKey: ["schedule"],
    queryFn: () => fetchClassSessions(),
  });
  const { data: myBookings } = useQuery({
    queryKey: ["my-bookings"],
    queryFn: fetchMyBookings,
    enabled: canBook,
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["schedule"] });
    queryClient.invalidateQueries({ queryKey: ["my-bookings"] });
  };
  const onError = (err: { response?: { data?: { detail?: string } } }) =>
    setError(err.response?.data?.detail ?? "That didn't work. Try again.");

  const bookMutation = useMutation({
    mutationFn: bookClass,
    onSuccess: () => {
      setError("");
      refresh();
    },
    onError,
  });
  const cancelMutation = useMutation({
    mutationFn: cancelBooking,
    onSuccess: () => {
      setError("");
      refresh();
    },
    onError,
  });

  const pending = bookMutation.isPending || cancelMutation.isPending;
  const upcoming = myBookings?.filter((b) => new Date(b.date) >= new Date(new Date().toDateString()));

  return (
    <div>
      <PageHeader title="Upcoming Sessions" subtitle="Classes scheduled at the gym." />

      {canBook && upcoming && upcoming.length > 0 && (
        <Card accent={railColor(0)} className="mb-6">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            My bookings
          </h2>
          <ul className="flex flex-col">
            {upcoming.map((b) => (
              <li
                key={b.id}
                className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border)] py-2 text-sm last:border-none"
              >
                <span className="text-[var(--color-text)]">{b.session_title}</span>
                <span className="text-[var(--color-text-muted)]">
                  {dayLabel(b.date)} · {b.start_time.slice(0, 5)}
                  {b.status === "waitlisted" && (
                    <span style={{ color: "var(--color-accent-2)" }}> · waitlist #{b.position}</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <ErrorText>{error}</ErrorText>

      {isLoading ? (
        <LoadingState />
      ) : isError ? (
        <ErrorState />
      ) : sessions?.length === 0 ? (
        <EmptyState>Nothing scheduled yet.</EmptyState>
      ) : (
        /* Two to a row from `sm` up, so a full timetable is a glance rather
           than a scroll. Each card carries its own rail colour so the list
           reads as a set of distinct sessions instead of one striped block. */
        <motion.div
          className="grid gap-3 sm:grid-cols-2"
          initial="hidden"
          animate="visible"
          variants={staggerContainer()}
        >
          {sessions?.map((s, index) => {
            const isPast = new Date(`${s.date}T${s.end_time}`) < new Date();
            const booked = s.my_status === "booked" || s.my_status === "attended";
            const waitlisted = s.my_status === "waitlisted";
            const full = s.spots_left === 0;

            return (
              <motion.div key={s.id} variants={fadeUp} className="h-full">
                <Card
                  accent={railColor(index)}
                  className="flex h-full flex-col gap-3 p-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h2 className="truncate font-semibold text-[var(--color-text)]">{s.title}</h2>
                      {s.instructor_name && (
                        <p className="truncate text-xs text-[var(--color-text-muted)]">
                          with {s.instructor_name}
                        </p>
                      )}
                    </div>
                    {/* Date and time on the right, where the eye already goes
                        for the seat count below it. */}
                    <div className="shrink-0 text-right text-xs text-[var(--color-text)]">
                      <p className="font-semibold">{dayLabel(s.date)}</p>
                      <p className="text-[var(--color-text-muted)]">
                        {s.start_time.slice(0, 5)} - {s.end_time.slice(0, 5)}
                      </p>
                    </div>
                  </div>

                  {s.description && (
                    <p className="line-clamp-2 text-xs text-[var(--color-text-muted)]">
                      {s.description}
                    </p>
                  )}

                  {/* mt-auto pins this row to the bottom, so cards in a row
                      line their seat counts and buttons up with each other
                      however long the titles above them run. */}
                  <div className="mt-auto flex items-center justify-between gap-3 pt-1">
                    <SeatCount session={s} />

                    {canBook && !isPast ? (
                      booked || waitlisted ? (
                        <span className="flex shrink-0 items-center gap-2">
                          <span
                            className="text-[11px] font-semibold uppercase tracking-wide"
                            style={{ color: waitlisted ? "var(--color-accent-2)" : "#22c55e" }}
                          >
                            {waitlisted ? "Waitlisted" : "Booked"}
                          </span>
                          <Button
                            variant="secondary"
                            onClick={() => cancelMutation.mutate(s.id)}
                            disabled={pending}
                            className="px-3 py-1 text-xs"
                          >
                            Cancel
                          </Button>
                        </span>
                      ) : (
                        <Button
                          onClick={() => bookMutation.mutate(s.id)}
                          disabled={pending}
                          className="shrink-0 px-3 py-1 text-xs"
                        >
                          {full ? "Join waitlist" : "Book"}
                        </Button>
                      )
                    ) : (
                      isPast && (
                        <span className="text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">
                          Finished
                        </span>
                      )
                    )}
                  </div>
                </Card>
              </motion.div>
            );
          })}
        </motion.div>
      )}
    </div>
  );
}
