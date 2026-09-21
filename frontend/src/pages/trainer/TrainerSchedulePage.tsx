import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useState } from "react";
import {
  createClassSession,
  deleteClassSession,
  fetchClassSessions,
  fetchRoster,
  markAttendance,
} from "../../api/schedule";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  ErrorText,
  Input,
  LoadingState,
  PageHeader,
  Textarea,
  tableCellClass,
  tableHeadCellClass,
  tableHeadRowClass,
  tableRowClass,
} from "../../components/ui";
import { serverMessage } from "../../lib/apiError";
import { classTimeProblem } from "../../lib/classTimes";
import { fadeUp, staggerContainer } from "../../lib/motion";
import { railColor } from "../../lib/theme";
import { askConfirm } from "../../store/confirmStore";

const emptyForm = {
  title: "",
  date: "",
  start_time: "",
  end_time: "",
  capacity: "",
  description: "",
};

export default function TrainerSchedulePage() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(emptyForm);
  const [error, setError] = useState("");
  const [rosterFor, setRosterFor] = useState<number | null>(null);

  const { data: classes, isLoading, isError } = useQuery({
    queryKey: ["trainer", "classes"],
    queryFn: () => fetchClassSessions(true),
  });

  // Said as soon as both times are in, rather than after a round trip.
  const timeProblem = classTimeProblem(form.start_time, form.end_time);

  const addClass = useMutation({
    mutationFn: () =>
      createClassSession({
        title: form.title,
        date: form.date,
        start_time: form.start_time,
        end_time: form.end_time,
        capacity: form.capacity ? Number(form.capacity) : null,
        description: form.description,
        // The backend stamps the signed-in trainer onto the class.
        trainer: null,
      }),
    onSuccess: () => {
      setForm(emptyForm);
      setError("");
      queryClient.invalidateQueries({ queryKey: ["trainer", "classes"] });
    },
    onError: (err) =>
      setError(serverMessage(err, "Could not create that class. Check the date and times.")),
  });

  const removeClass = useMutation({
    mutationFn: (id: number) => deleteClassSession(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["trainer", "classes"] }),
  });

  return (
    <div>
      <PageHeader title="My Classes" subtitle="The sessions you are running." />

      <Card accent={railColor(0)} className="mb-6">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Add a class
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Input
            placeholder="Title"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
          <Input
            type="date"
            aria-label="Date"
            value={form.date}
            onChange={(e) => setForm({ ...form, date: e.target.value })}
          />
          <Input
            type="number"
            placeholder="Capacity"
            value={form.capacity}
            onChange={(e) => setForm({ ...form, capacity: e.target.value })}
          />
          <Input
            type="time"
            aria-label="Start time"
            value={form.start_time}
            onChange={(e) => setForm({ ...form, start_time: e.target.value })}
          />
          <Input
            type="time"
            aria-label="End time"
            aria-invalid={Boolean(timeProblem)}
            value={form.end_time}
            onChange={(e) => setForm({ ...form, end_time: e.target.value })}
          />
        </div>
        {timeProblem && <ErrorText>{timeProblem}</ErrorText>}
        <Textarea
          placeholder="Description"
          rows={2}
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
          className="mt-3"
        />
        <div className="mt-3 flex items-center gap-3">
          <Button
            onClick={() => addClass.mutate()}
            disabled={
              !form.title ||
              !form.date ||
              !form.start_time ||
              !form.end_time ||
              Boolean(timeProblem) ||
              addClass.isPending
            }
          >
            {addClass.isPending ? "Adding..." : "Add class"}
          </Button>
          <ErrorText>{error}</ErrorText>
        </div>
      </Card>

      <Card accent={railColor(1)}>
        {isLoading ? (
          <LoadingState />
        ) : isError ? (
          <ErrorState />
        ) : !classes?.length ? (
          <EmptyState>You have no classes scheduled.</EmptyState>
        ) : (
          <div className="no-scrollbar overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-[var(--color-text-muted)]">
                <tr className={tableHeadRowClass}>
                  <th className={tableHeadCellClass}>Title</th>
                  <th className={tableHeadCellClass}>Date</th>
                  <th className={tableHeadCellClass}>Time</th>
                  <th className={tableHeadCellClass}>Booked</th>
                  <th className={tableHeadCellClass} />
                </tr>
              </thead>
              <motion.tbody initial="hidden" animate="visible" variants={staggerContainer(0.03)}>
                {classes.map((c) => (
                  <motion.tr key={c.id} variants={fadeUp} className={tableRowClass}>
                    <td className={tableCellClass}>{c.title}</td>
                    <td className={tableCellClass}>{new Date(c.date).toLocaleDateString()}</td>
                    <td className={tableCellClass}>
                      {c.start_time.slice(0, 5)} - {c.end_time.slice(0, 5)}
                    </td>
                    <td className={tableCellClass}>
                      {c.booked_count}
                      {c.capacity != null && ` / ${c.capacity}`}
                    </td>
                    <td className={`${tableCellClass} flex gap-2`}>
                      <Button
                        variant="secondary"
                        onClick={() => setRosterFor(rosterFor === c.id ? null : c.id)}
                      >
                        {rosterFor === c.id ? "Hide" : "Roster"}
                      </Button>
                      <Button
                        variant="danger"
                        onClick={() =>
                        askConfirm({
                          title: `Delete "${c.title}"?`,
                          consequence: "Anyone booked onto this class loses their place.",
                          run: () => removeClass.mutate(c.id),
                        })
                      }
                        disabled={removeClass.isPending}
                      >
                        Remove
                      </Button>
                    </td>
                  </motion.tr>
                ))}
              </motion.tbody>
            </table>
          </div>
        )}
      </Card>

      {rosterFor !== null && <RosterPanel sessionId={rosterFor} />}
    </div>
  );
}

/** Who is coming to one class, with a way to mark off who turned up. */
function RosterPanel({ sessionId }: { sessionId: number }) {
  const queryClient = useQueryClient();
  const [picked, setPicked] = useState<number[]>([]);

  const { data: roster, isLoading } = useQuery({
    queryKey: ["roster", sessionId],
    queryFn: () => fetchRoster(sessionId),
  });

  const mark = useMutation({
    mutationFn: () => markAttendance(sessionId, picked),
    onSuccess: () => {
      setPicked([]);
      queryClient.invalidateQueries({ queryKey: ["roster", sessionId] });
      queryClient.invalidateQueries({ queryKey: ["trainer", "classes"] });
    },
  });

  const toggle = (id: number) =>
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));

  const booked = roster?.filter((b) => b.status !== "waitlisted") ?? [];
  const waiting = roster?.filter((b) => b.status === "waitlisted") ?? [];

  return (
    <Card accent={railColor(2)} className="mt-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
        Class roster
      </h2>
      {isLoading ? (
        <LoadingState />
      ) : !roster?.length ? (
        <EmptyState>Nobody has booked this class yet.</EmptyState>
      ) : (
        <>
          <ul className="flex flex-col">
            {booked.map((b) => (
              <li
                key={b.id}
                className="flex items-center justify-between gap-3 border-b border-[var(--color-border)] py-2 text-sm last:border-none"
              >
                <label className="flex items-center gap-2 text-[var(--color-text)]">
                  <input
                    type="checkbox"
                    checked={picked.includes(b.member) || b.status === "attended"}
                    disabled={b.status === "attended"}
                    onChange={() => toggle(b.member)}
                    className="accent-[var(--color-accent)]"
                  />
                  {b.member_name}
                </label>
                <span
                  className="text-xs uppercase tracking-wide"
                  style={{ color: b.status === "attended" ? "#22c55e" : "var(--color-text-muted)" }}
                >
                  {b.status}
                </span>
              </li>
            ))}
          </ul>

          {waiting.length > 0 && (
            <div className="mt-4 border-t border-[var(--color-border)] pt-3">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                Waitlist
              </p>
              <ul className="flex flex-col gap-1">
                {waiting.map((b) => (
                  <li key={b.id} className="text-sm text-[var(--color-text-muted)]">
                    #{b.position} {b.member_name}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <Button
            variant="success"
            onClick={() => mark.mutate()}
            disabled={!picked.length || mark.isPending}
            className="mt-4"
          >
            {mark.isPending ? "Saving..." : `Mark ${picked.length} attended`}
          </Button>
        </>
      )}
    </Card>
  );
}
