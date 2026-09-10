import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { checkIn, checkOut, fetchCurrentCheckIn } from "../api/attendance";
import { fetchTodayDiet } from "../api/nutrition";
import { fetchTodaySplit } from "../api/workouts";
import { FALLBACK_MUSCLE_COLOR, MUSCLE_COLORS } from "../lib/theme";
import { Button, Card } from "./ui";

function formatElapsed(sinceIso: string) {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(sinceIso).getTime()) / 1000));
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

/** What today's plan is, shown right where the member checks in. */
function TodaySplit() {
  const { data } = useQuery({
    queryKey: ["splits", "today"],
    queryFn: () => fetchTodaySplit(),
  });

  if (!data) return null;

  if (!data.has_split) {
    return (
      <p className="text-sm text-[var(--color-text-muted)]">
        No split set up yet —{" "}
        <Link to="/split" className="text-[var(--color-accent)] hover:underline">
          plan your week
        </Link>
        .
      </p>
    );
  }

  if (!data.is_training_day) {
    return (
      <p className="text-sm text-[var(--color-text-muted)]">
        <span className="text-[var(--color-text)]">Rest day</span> — nothing scheduled for{" "}
        {data.weekday_name}.
      </p>
    );
  }

  const day = data.day!;
  return (
    <div className="w-full text-left">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          {data.weekday_name} — today's split
        </p>
        <Link
          to="/split"
          className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-accent)]"
        >
          Edit
        </Link>
      </div>

      <p className="font-display text-2xl leading-none text-[var(--color-text)]">
        {day.display_label}
      </p>

      <div className="mt-2 flex flex-wrap gap-1.5">
        {day.target_muscles.map((muscle) => {
          const colour = MUSCLE_COLORS[muscle] ?? FALLBACK_MUSCLE_COLOR;
          return (
            <span
              key={muscle}
              className="rounded-full px-2.5 py-0.5 text-[11px] font-semibold"
              style={{ background: colour, color: "#fff" }}
            >
              {muscle}
            </span>
          );
        })}
      </div>

      {day.exercises.length > 0 ? (
        <ul className="mt-3 flex flex-col">
          {day.exercises.map((ex) => (
            <li
              key={ex.id}
              className="flex items-center justify-between gap-2 border-b border-[var(--color-border)] py-1.5 text-sm last:border-none"
            >
              <span className="min-w-0 truncate text-[var(--color-text)]">{ex.exercise_name}</span>
              {(ex.target_sets || ex.target_reps) && (
                <span className="shrink-0 text-xs text-[var(--color-text-muted)]">
                  {ex.target_sets ?? "-"} x {ex.target_reps || "-"}
                </span>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-[var(--color-text-muted)]">
          No exercises added to this day yet.
        </p>
      )}
    </div>
  );
}

/** What today's meals are, shown alongside the training plan. */
function TodayDiet() {
  const { data } = useQuery({
    queryKey: ["diet", "today"],
    queryFn: () => fetchTodayDiet(),
  });

  if (!data || !data.has_plan) return null;

  if (!data.is_planned_day) {
    return (
      <p className="text-sm text-[var(--color-text-muted)]">
        Nothing planned to eat on {data.weekday_name}.
      </p>
    );
  }

  const day = data.day!;
  return (
    <div className="w-full text-left">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Today's food — {Math.round(Number(day.macros.calories))} kcal
        </p>
        <Link
          to="/diet"
          className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-accent)]"
        >
          Edit
        </Link>
      </div>
      <ul className="flex flex-col">
        {day.meals.map((meal) => (
          <li
            key={meal.id}
            className="flex items-baseline justify-between gap-2 border-b border-[var(--color-border)] py-1.5 text-sm last:border-none"
          >
            <span className="min-w-0 truncate text-[var(--color-text)]">
              {meal.meal_type_name}
              {meal.items.length > 0 && (
                <span className="text-[var(--color-text-muted)]">
                  {" "}
                  — {meal.items.map((i) => i.food_name).join(", ")}
                </span>
              )}
            </span>
            <span className="shrink-0 text-xs text-[var(--color-text-muted)]">
              {Math.round(Number(meal.macros.calories))} kcal
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function CheckInButton() {
  const queryClient = useQueryClient();
  const { data: current, isLoading } = useQuery({
    queryKey: ["attendance", "current"],
    queryFn: fetchCurrentCheckIn,
  });
  const [, forceTick] = useState(0);

  useEffect(() => {
    if (!current) return;
    const interval = setInterval(() => forceTick((n) => n + 1), 1000);
    return () => clearInterval(interval);
  }, [current]);

  const checkInMutation = useMutation({
    mutationFn: checkIn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["attendance"] }),
  });
  const checkOutMutation = useMutation({
    mutationFn: checkOut,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["attendance"] }),
  });

  const busy = checkInMutation.isPending || checkOutMutation.isPending || isLoading;

  return (
    <Card accent={"var(--color-accent)"} className="flex flex-col items-center gap-4 py-10 text-center">
      {current ? (
        <>
          <p className="text-sm uppercase tracking-wide text-[var(--color-text-muted)]">Checked in since</p>
          <p className="text-lg text-[var(--color-text)]">
            {new Date(current.check_in_time).toLocaleTimeString()}
          </p>
          <p className="font-mono text-4xl font-bold text-[var(--color-accent)]">
            {formatElapsed(current.check_in_time)}
          </p>
          {/* Ending a visit destroys nothing -- it was wearing the delete
              colour. Neutral: routine, and not the action being encouraged. */}
          <Button
            variant="secondary"
            disabled={busy}
            onClick={() => checkOutMutation.mutate()}
            className="w-48 py-3 text-base"
          >
            {checkOutMutation.isPending ? "Checking out..." : "Check Out"}
          </Button>
        </>
      ) : (
        <>
          <p className="text-sm uppercase tracking-wide text-[var(--color-text-muted)]">Status</p>
          <p className="text-lg text-[var(--color-text)]">Not checked in</p>
          {/* The positive action on this screen, and the one we want tapped. */}
          <Button
            variant="success"
            disabled={busy}
            onClick={() => checkInMutation.mutate()}
            className="w-48 py-3 text-base"
          >
            {checkInMutation.isPending ? "Checking in..." : "Check In"}
          </Button>
        </>
      )}
      {(checkInMutation.isError || checkOutMutation.isError) && (
        <p className="text-sm text-red-400">Something went wrong -- try again.</p>
      )}

      <div className="mt-2 w-full border-t border-[var(--color-border)] pt-4">
        <TodaySplit />
      </div>

      <div className="w-full border-t border-[var(--color-border)] pt-4">
        <TodayDiet />
      </div>
    </Card>
  );
}
