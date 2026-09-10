import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  bookPTSession,
  cancelPTSession,
  fetchPTSessions,
  fetchSlots,
  type PTSession,
} from "../api/pt";
import { fetchInstructors } from "../api/instructors";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  ErrorText,
  Input,
  LoadingState,
  PageHeader,
  Select,
} from "../components/ui";
import { isoDaysFromNow, todayIso } from "../lib/dates";
import { railColor } from "../lib/theme";
import { useAuthStore } from "../store/authStore";

const hhmm = (t: string) => t.slice(0, 5);

const STATUS_COLOUR: Record<string, string> = {
  booked: "#22c55e",
  completed: "#22c55e",
  cancelled: "#9494a8",
  no_show: "#ffb020",
};

function SessionRow({ session, onCancel }: { session: PTSession; onCancel: () => void }) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border)] py-2 text-sm last:border-none">
      <span className="min-w-0">
        <span className="block text-[var(--color-text)]">
          {new Date(session.date).toLocaleDateString(undefined, {
            weekday: "short",
            day: "numeric",
            month: "short",
          })}{" "}
          · {hhmm(session.start_time)}–{hhmm(session.end_time)}
        </span>
        <span className="block text-xs text-[var(--color-text-muted)]">
          with {session.trainer_name}
        </span>
      </span>
      <span className="flex items-center gap-3">
        <span
          className="text-[11px] font-semibold uppercase tracking-wide"
          style={{ color: STATUS_COLOUR[session.status] }}
        >
          {session.status_name}
        </span>
        {session.status === "booked" && !session.is_past && (
          <Button variant="secondary" onClick={onCancel} className="px-3 py-1 text-xs">
            Cancel
          </Button>
        )}
      </span>
    </li>
  );
}

export default function BookTrainerPage() {
  const queryClient = useQueryClient();
  const me = useAuthStore((s) => s.user);
  const [trainerId, setTrainerId] = useState<number | "">("");
  const [date, setDate] = useState(isoDaysFromNow(1));
  const [error, setError] = useState("");

  // Instructors carry the public-facing trainer profile, and each is linked to
  // the account that actually takes the session.
  const { data: instructors } = useQuery({
    queryKey: ["instructors"],
    queryFn: fetchInstructors,
  });
  const bookable = (instructors ?? []).filter((i) => i.user);

  const { data: slots, isLoading: slotsLoading } = useQuery({
    queryKey: ["pt", "slots", trainerId, date],
    queryFn: () => fetchSlots(Number(trainerId), date),
    enabled: trainerId !== "",
  });

  const { data: sessions, isLoading, isError } = useQuery({
    queryKey: ["pt", "sessions"],
    queryFn: () => fetchPTSessions(),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["pt"] });

  const book = useMutation({
    mutationFn: (slot: { start_time: string; end_time: string }) =>
      bookPTSession({
        trainer: Number(trainerId),
        member: me!.id,
        date,
        start_time: slot.start_time,
        end_time: slot.end_time,
      }),
    onSuccess: () => {
      setError("");
      invalidate();
    },
    onError: (err: { response?: { data?: { detail?: string } } }) =>
      setError(err.response?.data?.detail ?? "Could not book that slot."),
  });

  const cancel = useMutation({
    mutationFn: cancelPTSession,
    onSuccess: () => {
      setError("");
      invalidate();
    },
  });

  const upcoming = (sessions ?? []).filter(
    (s) => s.status === "booked" && !s.is_past
  );
  const past = (sessions ?? []).filter((s) => s.status !== "booked" || s.is_past);

  return (
    <div>
      <PageHeader
        title="Book a Trainer"
        subtitle="One-to-one sessions, in your trainer's own hours."
      />

      <Card accent={railColor(0)} className="mb-6">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Find a slot
        </h2>
        <div className="flex flex-wrap gap-3">
          <Select
            value={trainerId}
            onChange={(e) => {
              setTrainerId(Number(e.target.value) || "");
              setError("");
            }}
            className="max-w-[260px]"
          >
            <option value="">Choose a trainer</option>
            {bookable.map((instructor) => (
              <option key={instructor.id} value={instructor.user!}>
                {instructor.name} — {instructor.specialty}
              </option>
            ))}
          </Select>
          <Input
            type="date"
            value={date}
            min={todayIso()}
            onChange={(e) => setDate(e.target.value)}
            className="max-w-[180px]"
          />
        </div>

        <div className="mt-4">
          {trainerId === "" ? (
            <p className="text-sm text-[var(--color-text-muted)]">
              Pick a trainer to see when they are free.
            </p>
          ) : slotsLoading ? (
            <LoadingState />
          ) : !slots?.results.length ? (
            <EmptyState>
              Nothing free that day. Try another date — trainers set their own weekly hours.
            </EmptyState>
          ) : (
            <div className="flex flex-wrap gap-2">
              {slots.results.map((slot) => (
                <Button
                  key={slot.start_time}
                  variant="secondary"
                  onClick={() => book.mutate(slot)}
                  disabled={book.isPending}
                  className="px-3 py-1.5 text-sm"
                >
                  {hhmm(slot.start_time)}–{hhmm(slot.end_time)}
                </Button>
              ))}
            </div>
          )}
          <ErrorText>{error}</ErrorText>
        </div>
      </Card>

      <div className="grid gap-6 md:grid-cols-2">
        <Card accent={railColor(2)}>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            Coming up
          </h2>
          {isLoading ? (
            <LoadingState />
          ) : isError ? (
            <ErrorState />
          ) : !upcoming.length ? (
            <EmptyState>Nothing booked yet.</EmptyState>
          ) : (
            <ul className="flex flex-col">
              {upcoming.map((session) => (
                <SessionRow
                  key={session.id}
                  session={session}
                  onCancel={() => cancel.mutate(session.id)}
                />
              ))}
            </ul>
          )}
        </Card>

        <Card accent={railColor(4)}>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            Past sessions
          </h2>
          {!past.length ? (
            <EmptyState>Nothing yet.</EmptyState>
          ) : (
            <ul className="flex flex-col">
              {past.slice(0, 10).map((session) => (
                <SessionRow key={session.id} session={session} onCancel={() => {}} />
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
