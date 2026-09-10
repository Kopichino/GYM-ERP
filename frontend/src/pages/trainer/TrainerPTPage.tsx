import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  addAvailability,
  addUnavailable,
  cancelPTSession,
  completePTSession,
  deleteAvailability,
  deleteUnavailable,
  fetchAvailability,
  fetchPTSessions,
  fetchUnavailable,
} from "../../api/pt";
import { WEEKDAYS } from "../../api/workouts";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  ErrorText,
  Input,
  LoadingState,
  PageHeader,
  Select, ghostButtonClass } from "../../components/ui";
import { isoDaysFromNow } from "../../lib/dates";
import { railColor } from "../../lib/theme";

const LABEL = "mb-1 block text-xs uppercase tracking-wide text-[var(--color-text-muted)]";
const hhmm = (t: string) => t.slice(0, 5);

const STATUS_COLOUR: Record<string, string> = {
  booked: "#22c55e",
  completed: "#22c55e",
  cancelled: "#9494a8",
  no_show: "#ffb020",
};

export default function TrainerPTPage() {
  const queryClient = useQueryClient();
  const [window, setWindow] = useState({ weekday: "0", start_time: "09:00", end_time: "12:00" });
  const [block, setBlock] = useState({ date: isoDaysFromNow(1), reason: "" });
  const [error, setError] = useState("");

  const { data: availability, isLoading } = useQuery({
    queryKey: ["pt", "availability"],
    queryFn: () => fetchAvailability(),
  });
  const { data: blocked } = useQuery({
    queryKey: ["pt", "unavailable"],
    queryFn: fetchUnavailable,
  });
  const { data: sessions, isError } = useQuery({
    queryKey: ["pt", "sessions"],
    queryFn: () => fetchPTSessions(),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["pt"] });
  const fail = (fallback: string) => (err: { response?: { data?: Record<string, unknown> } }) => {
    const data = err.response?.data;
    const first = data && Object.values(data)[0];
    setError(String(Array.isArray(first) ? first[0] : (first ?? fallback)));
  };

  const addWindow = useMutation({
    mutationFn: () =>
      addAvailability({
        weekday: Number(window.weekday),
        start_time: window.start_time,
        end_time: window.end_time,
      }),
    onSuccess: () => {
      setError("");
      invalidate();
    },
    onError: fail("Could not add those hours."),
  });
  const removeWindow = useMutation({ mutationFn: deleteAvailability, onSuccess: invalidate });

  const addBlock = useMutation({
    mutationFn: () => addUnavailable(block),
    onSuccess: () => {
      setBlock({ ...block, reason: "" });
      setError("");
      invalidate();
    },
    onError: fail("Could not block that day."),
  });
  const removeBlock = useMutation({ mutationFn: deleteUnavailable, onSuccess: invalidate });

  const cancel = useMutation({ mutationFn: cancelPTSession, onSuccess: invalidate });
  const close = useMutation({
    mutationFn: ({ id, noShow }: { id: number; noShow?: boolean }) =>
      completePTSession(id, { no_show: noShow, is_paid: !noShow }),
    onSuccess: invalidate,
  });

  const upcoming = (sessions ?? []).filter((s) => s.status === "booked" && !s.is_past);
  const toClose = (sessions ?? []).filter((s) => s.status === "booked" && s.is_past);
  const done = (sessions ?? []).filter((s) => s.status !== "booked");

  return (
    <div>
      <PageHeader
        title="Personal Training"
        subtitle="Your hours, your days off, and your one-to-one diary."
      />

      <div className="mb-6 grid gap-6 lg:grid-cols-2">
        <Card accent={railColor(0)}>
          <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            Your weekly hours
          </h2>
          <p className="mb-4 text-sm text-[var(--color-text-muted)]">
            Set once and it repeats. Members only ever see slots inside these windows, minus
            anything already booked.
          </p>

          <div className="flex flex-wrap gap-2">
            <div className="min-w-[130px] flex-1">
              <label htmlFor="pt-weekday" className={LABEL}>
                Day
              </label>
              <Select
                id="pt-weekday"
                value={window.weekday}
                onChange={(e) => setWindow({ ...window, weekday: e.target.value })}
              >
                {WEEKDAYS.map((label, index) => (
                  <option key={label} value={index}>
                    {label}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <label htmlFor="pt-from" className={LABEL}>
                From
              </label>
              <Input
                id="pt-from"
                type="time"
                value={window.start_time}
                onChange={(e) => setWindow({ ...window, start_time: e.target.value })}
                className="w-[120px]"
              />
            </div>
            <div>
              <label htmlFor="pt-to" className={LABEL}>
                Until
              </label>
              <Input
                id="pt-to"
                type="time"
                value={window.end_time}
                onChange={(e) => setWindow({ ...window, end_time: e.target.value })}
                className="w-[120px]"
              />
            </div>
            <Button
              onClick={() => addWindow.mutate()}
              disabled={addWindow.isPending}
              className="self-end"
            >
              Add
            </Button>
          </div>

          <div className="mt-4 border-t border-[var(--color-border)] pt-3">
            {isLoading ? (
              <LoadingState />
            ) : !availability?.length ? (
              <EmptyState>No hours set — members cannot book you yet.</EmptyState>
            ) : (
              <ul className="flex flex-col">
                {availability.map((row) => (
                  <li
                    key={row.id}
                    className="flex items-center justify-between gap-2 border-b border-[var(--color-border)] py-2 text-sm last:border-none"
                  >
                    <span className="text-[var(--color-text)]">
                      {row.weekday_name}
                      <span className="ml-2 tabular-nums text-[var(--color-text-muted)]">
                        {hhmm(row.start_time)}–{hhmm(row.end_time)}
                      </span>
                    </span>
                    <button
                      onClick={() => removeWindow.mutate(row.id)}
                      className={ghostButtonClass}
                    >
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <ErrorText>{error}</ErrorText>
        </Card>

        <Card accent={railColor(3)}>
          <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            Days off
          </h2>
          <p className="mb-4 text-sm text-[var(--color-text-muted)]">
            Blocks a single day without touching your weekly pattern — so the following week is
            still bookable.
          </p>
          <div className="flex flex-wrap gap-2">
            <Input
              type="date"
              value={block.date}
              onChange={(e) => setBlock({ ...block, date: e.target.value })}
              className="w-[170px]"
            />
            <Input
              placeholder="Reason (optional)"
              value={block.reason}
              onChange={(e) => setBlock({ ...block, reason: e.target.value })}
              className="min-w-[140px] flex-1"
            />
            <Button onClick={() => addBlock.mutate()} disabled={addBlock.isPending}>
              Block
            </Button>
          </div>

          <div className="mt-4 border-t border-[var(--color-border)] pt-3">
            {!blocked?.length ? (
              <EmptyState>No days blocked.</EmptyState>
            ) : (
              <ul className="flex flex-col">
                {blocked.map((row) => (
                  <li
                    key={row.id}
                    className="flex items-center justify-between gap-2 border-b border-[var(--color-border)] py-2 text-sm last:border-none"
                  >
                    <span className="text-[var(--color-text)]">
                      {new Date(row.date).toLocaleDateString()}
                      {row.reason && (
                        <span className="ml-2 text-xs text-[var(--color-text-muted)]">
                          {row.reason}
                        </span>
                      )}
                    </span>
                    <button
                      onClick={() => removeBlock.mutate(row.id)}
                      className={ghostButtonClass}
                    >
                      Remove
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Card>
      </div>

      {toClose.length > 0 && (
        <Card accent="#ffb020" className="mb-6">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            {toClose.length} session{toClose.length === 1 ? "" : "s"} to close off
          </h2>
          <ul className="flex flex-col">
            {toClose.map((session) => (
              <li
                key={session.id}
                className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border)] py-2 text-sm last:border-none"
              >
                <span className="text-[var(--color-text)]">
                  {session.member_name}
                  <span className="ml-2 text-xs text-[var(--color-text-muted)]">
                    {new Date(session.date).toLocaleDateString()} {hhmm(session.start_time)}
                  </span>
                </span>
                <span className="flex gap-2">
                  <Button
                    variant="success"
                    onClick={() => close.mutate({ id: session.id })}
                    className="px-3 py-1 text-xs"
                  >
                    Done
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => close.mutate({ id: session.id, noShow: true })}
                    className="px-3 py-1 text-xs"
                  >
                    No show
                  </Button>
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card accent={railColor(2)}>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Your diary
        </h2>
        {isError ? (
          <ErrorState />
        ) : !upcoming.length && !done.length ? (
          <EmptyState>Nothing booked yet.</EmptyState>
        ) : (
          <ul className="flex flex-col">
            {[...upcoming, ...done.slice(0, 10)].map((session) => (
              <li
                key={session.id}
                className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border)] py-2 text-sm last:border-none"
              >
                <span className="min-w-0">
                  <span className="block text-[var(--color-text)]">{session.member_name}</span>
                  <span className="block text-xs text-[var(--color-text-muted)]">
                    {new Date(session.date).toLocaleDateString(undefined, {
                      weekday: "short",
                      day: "numeric",
                      month: "short",
                    })}{" "}
                    · {hhmm(session.start_time)}–{hhmm(session.end_time)}
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
                    <Button
                      variant="secondary"
                      onClick={() => cancel.mutate(session.id)}
                      className="px-3 py-1 text-xs"
                    >
                      Cancel
                    </Button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
