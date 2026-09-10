import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useMemo, useState } from "react";
import { fetchCalendar } from "../api/attendance";
import { AnimatedNumber, Card } from "./ui";

const WEEKDAYS = ["S", "M", "T", "W", "T", "F", "S"];

interface DayCell {
  date: Date;
  iso: string;
}

function startOfMonth(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

function toIso(d: Date) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function FlameIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className}>
      <path
        fill="currentColor"
        d="M12 2c1 3-2 4-2 7a4 4 0 0 0 8 0c0-1-.5-2-1-2 1 4-1 5-2 5a2.5 2.5 0 0 1-2.5-2.5c0-2 1.5-2.5 1.5-5.5-2 1-5 3-5 7a5.5 5.5 0 0 0 11 0C20 6 15 4 12 2Z"
      />
    </svg>
  );
}

export default function ConsistencyCalendar() {
  const { data } = useQuery({ queryKey: ["attendance", "calendar"], queryFn: fetchCalendar });
  const [cursor, setCursor] = useState(() => startOfMonth(new Date()));

  const visitedDates = useMemo(() => new Set(data?.dates ?? []), [data]);
  const todayIso = toIso(new Date());
  const now = new Date();
  const isCurrentMonth = cursor.getFullYear() === now.getFullYear() && cursor.getMonth() === now.getMonth();

  const weeks = useMemo(() => {
    const daysInMonth = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0).getDate();
    const startWeekday = startOfMonth(cursor).getDay();

    const cells: (DayCell | null)[] = Array.from({ length: startWeekday }, () => null);
    for (let day = 1; day <= daysInMonth; day++) {
      const date = new Date(cursor.getFullYear(), cursor.getMonth(), day);
      cells.push({ date, iso: toIso(date) });
    }

    const rows: (DayCell | null)[][] = [];
    for (let i = 0; i < cells.length; i += 7) {
      rows.push(cells.slice(i, i + 7));
    }
    return rows;
  }, [cursor]);

  const monthLabel = cursor.toLocaleDateString(undefined, { month: "long", year: "numeric" });
  const monthPrefix = `${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2, "0")}`;
  const monthVisits = useMemo(
    () => [...visitedDates].filter((iso) => iso.startsWith(monthPrefix)).length,
    [visitedDates, monthPrefix]
  );

  return (
    <Card accent={"#ffb020"}>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            Consistency Calendar
          </h2>
          <p className="font-display text-2xl uppercase tracking-wide text-[var(--color-text)]">{monthLabel}</p>
        </div>
        <div className="flex gap-1">
          <button
            onClick={() => setCursor((c) => new Date(c.getFullYear(), c.getMonth() - 1, 1))}
            className="rounded-md border border-[var(--color-border)] px-2.5 py-1.5 text-[var(--color-text-muted)] transition-colors hover:border-[var(--color-accent)] hover:text-[var(--color-text)]"
            aria-label="Previous month"
          >
            &#8249;
          </button>
          <button
            onClick={() => setCursor((c) => new Date(c.getFullYear(), c.getMonth() + 1, 1))}
            disabled={isCurrentMonth}
            className="rounded-md border border-[var(--color-border)] px-2.5 py-1.5 text-[var(--color-text-muted)] transition-colors hover:border-[var(--color-accent)] hover:text-[var(--color-text)] disabled:cursor-not-allowed disabled:opacity-30"
            aria-label="Next month"
          >
            &#8250;
          </button>
        </div>
      </div>

      <div className="mb-2 grid grid-cols-7 gap-1 text-center text-[11px] font-semibold uppercase text-[var(--color-text-muted)]">
        {WEEKDAYS.map((w, i) => (
          <span key={i}>{w}</span>
        ))}
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={monthLabel}
          initial={{ opacity: 0, x: 12 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -12 }}
          transition={{ duration: 0.2 }}
          className="grid grid-cols-7 gap-1"
        >
          {weeks.flatMap((week, wi) =>
            week.map((cell, di) => {
              if (!cell) return <div key={`pad-${wi}-${di}`} />;
              const isVisited = visitedDates.has(cell.iso);
              const isToday = cell.iso === todayIso;
              const isFuture = cell.iso > todayIso;
              return (
                <div key={cell.iso} className="aspect-square">
                  <motion.div
                    initial={{ scale: 0.6, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    transition={{ duration: 0.15, delay: (wi * 7 + di) * 0.006 }}
                    className={`flex h-full w-full items-center justify-center rounded-lg text-xs font-semibold ${
                      isVisited
                        ? "bg-[var(--color-accent)] text-white shadow-[0_0_12px_-2px_var(--color-accent)]"
                        : isFuture
                          ? "text-[var(--color-text-muted)]/30"
                          : "bg-[var(--color-surface-2)] text-[var(--color-text-muted)]"
                    } ${isToday ? "ring-2 ring-[var(--color-accent-2)]" : ""}`}
                  >
                    {cell.date.getDate()}
                  </motion.div>
                </div>
              );
            })
          )}
        </motion.div>
      </AnimatePresence>

      <div className="mt-5 grid grid-cols-3 gap-3 border-t border-[var(--color-border)] pt-4 text-center">
        <div>
          <div className="flex items-center justify-center gap-1 text-[var(--color-accent)]">
            <FlameIcon className="h-5 w-5" />
            <span className="font-display text-2xl">
              <AnimatedNumber value={data?.current_streak ?? 0} />
            </span>
          </div>
          <p className="text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">Day streak</p>
        </div>
        <div>
          <p className="font-display text-2xl text-[var(--color-text)]">
            <AnimatedNumber value={data?.longest_streak ?? 0} />
          </p>
          <p className="text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">Best streak</p>
        </div>
        <div>
          <p className="font-display text-2xl text-[var(--color-text)]">
            <AnimatedNumber value={monthVisits} />
          </p>
          <p className="text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">This month</p>
        </div>
      </div>
    </Card>
  );
}
