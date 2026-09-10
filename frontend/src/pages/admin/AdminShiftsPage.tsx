import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  createShift,
  deleteShift,
  fetchOnFloor,
  fetchShifts,
  POSITIONS,
  type Position,
  type Shift,
} from "../../api/shifts";
import { fetchUsers } from "../../api/users";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  ErrorText,
  Input,
  LoadingState,
  Select, ghostButtonClass } from "../../components/ui";
import { railColor } from "../../lib/theme";
import { isoDate, weekStart } from "../../lib/dates";

const LABEL = "mb-1 block text-xs uppercase tracking-wide text-[var(--color-text-muted)]";


// Categorical, not status. These are job roles -- "gym floor" is not a danger
// state and "PT" is not good news -- so they deliberately avoid the four
// status hues and use the neutral end of the palette instead. Reusing red and
// green here was what made those colours ambiguous everywhere else.
const POSITION_COLOUR: Record<Position, string> = {
  floor: "#4f8dfd",
  front_desk: "#06b6d4",
  pt: "#a855f7",
  classes: "#8b5cf6",
  cleaning: "#64748b",
  management: "#0ea5e9",
};

const hhmm = (t: string) => t.slice(0, 5);

function ShiftChip({ shift, onRemove }: { shift: Shift; onRemove: () => void }) {
  const colour = POSITION_COLOUR[shift.position];
  return (
    <div
      className="group relative rounded-md px-2 py-1.5 text-xs"
      style={{ background: `${colour}22`, borderLeft: `3px solid ${colour}` }}
    >
      <span className="block truncate font-semibold text-[var(--color-text)]">
        {shift.staff_name}
      </span>
      <span className="block text-[var(--color-text-muted)]">
        {hhmm(shift.start_time)}–{hhmm(shift.end_time)} · {shift.position_name}
      </span>
      <button
        onClick={onRemove}
        aria-label={`Remove ${shift.staff_name}'s shift`}
        className={`${ghostButtonClass} absolute right-1 top-1`}
      >
        ×
      </button>
    </div>
  );
}

export default function AdminShiftsPage() {
  const queryClient = useQueryClient();
  const [monday, setMonday] = useState(() => weekStart(new Date()));
  const [form, setForm] = useState({
    staff: "" as number | "",
    date: isoDate(new Date()),
    start_time: "06:00",
    end_time: "14:00",
    position: "floor" as Position,
    notes: "",
  });
  const [error, setError] = useState("");

  const days = useMemo(
    () =>
      Array.from({ length: 7 }, (_, i) => {
        const d = new Date(monday);
        d.setDate(d.getDate() + i);
        return d;
      }),
    [monday]
  );
  const from = isoDate(days[0]);
  const to = isoDate(days[6]);

  const { data: shifts, isLoading, isError } = useQuery({
    queryKey: ["shifts", from, to],
    queryFn: () => fetchShifts({ from, to }),
  });
  const { data: onFloor } = useQuery({
    queryKey: ["shifts", "on-floor"],
    queryFn: fetchOnFloor,
    // The rota moves through the day whether or not anyone reloads.
    refetchInterval: 60_000,
  });
  const { data: trainers } = useQuery({
    queryKey: ["admin", "trainers"],
    queryFn: () => fetchUsers("trainer"),
  });
  const { data: admins } = useQuery({
    queryKey: ["admin", "admins"],
    queryFn: () => fetchUsers("admin"),
  });

  const staff = [...(trainers ?? []), ...(admins ?? [])];

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["shifts"] });

  const add = useMutation({
    mutationFn: () =>
      createShift({
        staff: Number(form.staff),
        date: form.date,
        start_time: form.start_time,
        end_time: form.end_time,
        position: form.position,
        notes: form.notes,
      }),
    onSuccess: () => {
      setError("");
      invalidate();
    },
    onError: (err: { response?: { data?: Record<string, unknown> } }) => {
      const data = err.response?.data;
      const first = data && Object.values(data)[0];
      setError(String(Array.isArray(first) ? first[0] : (first ?? "Could not save that shift.")));
    },
  });

  const remove = useMutation({ mutationFn: deleteShift, onSuccess: invalidate });

  const byDay = useMemo(() => {
    const map = new Map<string, Shift[]>();
    (shifts ?? []).forEach((s) => {
      const list = map.get(s.date);
      if (list) list.push(s);
      else map.set(s.date, [s]);
    });
    return map;
  }, [shifts]);

  const weekHours = (shifts ?? []).reduce((sum, s) => sum + s.hours, 0);

  function shiftWeek(delta: number) {
    const next = new Date(monday);
    next.setDate(next.getDate() + delta * 7);
    setMonday(next);
  }

  return (
    <div className="flex flex-col gap-6">
      <Card accent={railColor(2)}>
        <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          On the floor now
        </h2>
        <p className="mb-3 text-sm text-[var(--color-text-muted)]">
          Read straight off the rota — there is no "currently working" flag anyone has to
          remember to clear.
        </p>
        {!onFloor?.results.length ? (
          <EmptyState>Nobody is rostered at the moment.</EmptyState>
        ) : (
          <ul className="flex flex-wrap gap-2">
            {onFloor.results.map((s) => (
              <li
                key={s.id}
                className="rounded-md px-3 py-1.5 text-sm"
                style={{
                  background: `${POSITION_COLOUR[s.position]}22`,
                  color: "var(--color-text)",
                }}
              >
                {s.staff_name}
                <span className="ml-2 text-xs text-[var(--color-text-muted)]">
                  {s.position_name} · until {hhmm(s.end_time)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card accent={railColor(0)}>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Add a shift
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <label htmlFor="shift-staff" className={LABEL}>
              Who
            </label>
            <Select
              id="shift-staff"
              value={form.staff}
              onChange={(e) => setForm({ ...form, staff: Number(e.target.value) || "" })}
            >
              <option value="">Pick someone</option>
              {staff.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.username}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label htmlFor="shift-date" className={LABEL}>
              Day
            </label>
            <Input
              id="shift-date"
              type="date"
              value={form.date}
              onChange={(e) => setForm({ ...form, date: e.target.value })}
            />
          </div>
          <div>
            <label htmlFor="shift-position" className={LABEL}>
              Doing what
            </label>
            <Select
              id="shift-position"
              value={form.position}
              onChange={(e) => setForm({ ...form, position: e.target.value as Position })}
            >
              {POSITIONS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label htmlFor="shift-start" className={LABEL}>
              From
            </label>
            <Input
              id="shift-start"
              type="time"
              value={form.start_time}
              onChange={(e) => setForm({ ...form, start_time: e.target.value })}
            />
          </div>
          <div>
            <label htmlFor="shift-end" className={LABEL}>
              Until
            </label>
            <Input
              id="shift-end"
              type="time"
              value={form.end_time}
              onChange={(e) => setForm({ ...form, end_time: e.target.value })}
            />
          </div>
          <div>
            <label htmlFor="shift-notes" className={LABEL}>
              Notes
            </label>
            <Input
              id="shift-notes"
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
            />
          </div>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button onClick={() => add.mutate()} disabled={!form.staff || add.isPending}>
            {add.isPending ? "Saving..." : "Add to rota"}
          </Button>
          <span className="text-xs text-[var(--color-text-muted)]">
            Overnight shifts go in as two rows, one per day — which is also how they are paid.
          </span>
          <ErrorText>{error}</ErrorText>
        </div>
      </Card>

      <Card accent={railColor(1)}>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            Week of {days[0].toLocaleDateString(undefined, { day: "numeric", month: "long" })}
            <span className="ml-2 text-[var(--color-text)]">{weekHours.toFixed(1)}h rostered</span>
          </h2>
          <span className="flex gap-2">
            <Button variant="secondary" onClick={() => shiftWeek(-1)} className="px-3 py-1 text-xs">
              Previous
            </Button>
            <Button
              variant="secondary"
              onClick={() => setMonday(weekStart(new Date()))}
              className="px-3 py-1 text-xs"
            >
              This week
            </Button>
            <Button variant="secondary" onClick={() => shiftWeek(1)} className="px-3 py-1 text-xs">
              Next
            </Button>
          </span>
        </div>

        {isLoading ? (
          <LoadingState />
        ) : isError ? (
          <ErrorState />
        ) : (
          <div className="no-scrollbar grid gap-3 overflow-x-auto md:grid-cols-7">
            {days.map((day) => {
              const key = isoDate(day);
              const rows = byDay.get(key) ?? [];
              const isToday = key === isoDate(new Date());
              return (
                <div
                  key={key}
                  className="min-w-[130px] rounded-lg border p-2"
                  style={{
                    borderColor: isToday ? "var(--color-accent)" : "var(--color-border)",
                  }}
                >
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                    {day.toLocaleDateString(undefined, { weekday: "short" })}{" "}
                    <span className="text-[var(--color-text)]">{day.getDate()}</span>
                    {isToday && (
                      <span className="ml-1 text-[var(--color-accent)]">today</span>
                    )}
                  </p>
                  <div className="flex flex-col gap-1.5">
                    {rows.length === 0 ? (
                      <p className="text-xs text-[var(--color-text-muted)]">Nobody on</p>
                    ) : (
                      rows.map((shift) => (
                        <ShiftChip
                          key={shift.id}
                          shift={shift}
                          onRemove={() => remove.mutate(shift.id)}
                        />
                      ))
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}
