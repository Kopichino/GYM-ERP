import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  addSplitDay,
  addSplitExercise,
  createSplit,
  deleteSplitDay,
  deleteSplitExercise,
  fetchExercises,
  fetchSplits,
  updateSplitDay,
  WEEKDAYS,
  type Exercise,
  type SplitDay,
  type WorkoutSplit,
} from "../api/workouts";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  ErrorText,
  Input,
  LoadingState,
  PageHeader,
  Select, ghostButtonClass } from "../components/ui";
import { MUSCLE_COLORS, FALLBACK_MUSCLE_COLOR } from "../lib/theme";

const todayWeekday = () => (new Date().getDay() + 6) % 7; // JS Sunday=0 -> Monday=0

function MuscleChip({
  muscle,
  selected,
  onClick,
}: {
  muscle: string;
  selected?: boolean;
  onClick?: () => void;
}) {
  const colour = MUSCLE_COLORS[muscle] ?? FALLBACK_MUSCLE_COLOR;
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!onClick}
      className="rounded-full border px-3 py-1 text-xs font-semibold transition-colors disabled:cursor-default"
      style={{
        borderColor: colour,
        color: selected || !onClick ? "#fff" : colour,
        background: selected || !onClick ? colour : "transparent",
      }}
    >
      {muscle}
    </button>
  );
}

/** Target muscles first, then the exercises they unlock. */
function MusclePicker({
  muscles,
  chosen,
  onToggle,
}: {
  muscles: string[];
  chosen: string[];
  onToggle: (m: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {muscles.map((m) => (
        <MuscleChip
          key={m}
          muscle={m}
          selected={chosen.includes(m)}
          onClick={() => onToggle(m)}
        />
      ))}
    </div>
  );
}

function DayCard({
  weekday,
  day,
  split,
  exercises,
  muscles,
  isToday,
}: {
  weekday: number;
  day: SplitDay | undefined;
  split: WorkoutSplit;
  exercises: Exercise[];
  muscles: string[];
  isToday: boolean;
}) {
  const queryClient = useQueryClient();
  const [picking, setPicking] = useState(false);
  const [draftMuscles, setDraftMuscles] = useState<string[]>([]);
  const [draftLabel, setDraftLabel] = useState("");
  const [exerciseId, setExerciseId] = useState<number | "">("");
  const [sets, setSets] = useState("");
  const [reps, setReps] = useState("");
  const [error, setError] = useState("");

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["splits"] });
  const fail = (msg: string) => () => setError(msg);

  const createDay = useMutation({
    mutationFn: () =>
      addSplitDay({
        split: split.id,
        weekday,
        label: draftLabel,
        target_muscles: draftMuscles,
      }),
    onSuccess: () => {
      setPicking(false);
      setDraftMuscles([]);
      setDraftLabel("");
      setError("");
      refresh();
    },
    onError: fail("Could not add that day."),
  });

  const editMuscles = useMutation({
    mutationFn: (next: string[]) => updateSplitDay(day!.id, { target_muscles: next }),
    onSuccess: refresh,
  });
  const removeDay = useMutation({ mutationFn: () => deleteSplitDay(day!.id), onSuccess: refresh });
  const addExercise = useMutation({
    mutationFn: () =>
      addSplitExercise({
        day: day!.id,
        exercise: exerciseId as number,
        target_sets: sets ? Number(sets) : null,
        target_reps: reps,
      }),
    onSuccess: () => {
      setExerciseId("");
      setSets("");
      setReps("");
      setError("");
      refresh();
    },
    onError: fail("Could not add that exercise."),
  });
  const removeExercise = useMutation({ mutationFn: deleteSplitExercise, onSuccess: refresh });

  // The picker only offers what the day actually targets -- that's the whole
  // point of asking for muscles first.
  const shortlist = useMemo(() => {
    if (!day?.target_muscles.length) return exercises;
    const wanted = day.target_muscles.map((m) => m.toLowerCase());
    return exercises.filter((e) => wanted.includes((e.muscle_group ?? "").toLowerCase()));
  }, [day, exercises]);

  // Today's card is railed in the accent; the rest of the week sits quiet.
  return (
    <Card
      className="flex flex-col gap-3"
      accent={isToday ? "var(--color-accent)" : "var(--color-border)"}
    >
      <div className="flex items-center justify-between gap-2">
        <div>
          <h3 className="font-display text-2xl leading-none text-[var(--color-text)]">
            {WEEKDAYS[weekday]}
          </h3>
          {isToday && (
            <span className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-accent)]">
              Today
            </span>
          )}
        </div>
        {day && (
          <button
            onClick={() => removeDay.mutate()}
            className={ghostButtonClass}
          >
            Make rest day
          </button>
        )}
      </div>

      {!day && !picking && (
        <>
          <p className="text-sm text-[var(--color-text-muted)]">Rest day</p>
          <Button variant="secondary" onClick={() => setPicking(true)}>
            Add training day
          </Button>
        </>
      )}

      {!day && picking && (
        <div className="flex flex-col gap-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            1. Which muscles are you training?
          </p>
          <MusclePicker
            muscles={muscles}
            chosen={draftMuscles}
            onToggle={(m) =>
              setDraftMuscles((prev) =>
                prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m]
              )
            }
          />
          <Input
            placeholder="Name this day (optional) — e.g. Push"
            value={draftLabel}
            onChange={(e) => setDraftLabel(e.target.value)}
          />
          <div className="flex gap-2">
            <Button
              onClick={() => createDay.mutate()}
              disabled={!draftMuscles.length || createDay.isPending}
            >
              {createDay.isPending ? "Saving..." : "Save day"}
            </Button>
            <Button variant="secondary" onClick={() => setPicking(false)}>
              Cancel
            </Button>
          </div>
          <ErrorText>{error}</ErrorText>
        </div>
      )}

      {day && (
        <>
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              Target muscles
            </p>
            <MusclePicker
              muscles={muscles}
              chosen={day.target_muscles}
              onToggle={(m) =>
                editMuscles.mutate(
                  day.target_muscles.includes(m)
                    ? day.target_muscles.filter((x) => x !== m)
                    : [...day.target_muscles, m]
                )
              }
            />
          </div>

          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              Exercises ({day.exercises.length})
            </p>
            {day.exercises.length === 0 ? (
              <p className="text-sm text-[var(--color-text-muted)]">
                Nothing added yet.
              </p>
            ) : (
              <ul className="flex flex-col">
                {day.exercises.map((ex) => (
                  <li
                    key={ex.id}
                    className="flex items-center justify-between gap-2 border-b border-[var(--color-border)] py-2 text-sm last:border-none"
                  >
                    <span className="min-w-0 truncate text-[var(--color-text)]">
                      {ex.exercise_name}
                    </span>
                    <span className="flex shrink-0 items-center gap-3">
                      {(ex.target_sets || ex.target_reps) && (
                        <span className="text-xs text-[var(--color-text-muted)]">
                          {ex.target_sets ?? "-"} x {ex.target_reps || "-"}
                        </span>
                      )}
                      <button
                        onClick={() => removeExercise.mutate(ex.id)}
                        className={ghostButtonClass}
                      >
                        Remove
                      </button>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="flex flex-col gap-2 border-t border-[var(--color-border)] pt-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              2. Add an exercise
            </p>
            {day.target_muscles.length === 0 ? (
              <p className="text-sm text-[var(--color-text-muted)]">
                Pick a target muscle first.
              </p>
            ) : (
              <>
                <Select
                  value={exerciseId}
                  onChange={(e) => setExerciseId(Number(e.target.value) || "")}
                >
                  <option value="">
                    Select from {shortlist.length} {day.target_muscles.join(" / ")} exercises
                  </option>
                  {shortlist.map((ex) => (
                    <option key={ex.id} value={ex.id}>
                      {ex.name}
                    </option>
                  ))}
                </Select>
                <div className="flex gap-2">
                  <Input
                    type="number"
                    min={1}
                    placeholder="Sets"
                    value={sets}
                    onChange={(e) => setSets(e.target.value)}
                    className="w-20"
                  />
                  <Input
                    placeholder="Reps (e.g. 8-12)"
                    value={reps}
                    onChange={(e) => setReps(e.target.value)}
                    className="flex-1"
                  />
                  <Button
                    onClick={() => addExercise.mutate()}
                    disabled={!exerciseId || addExercise.isPending}
                  >
                    Add
                  </Button>
                </div>
              </>
            )}
            <ErrorText>{error}</ErrorText>
          </div>
        </>
      )}
    </Card>
  );
}

export default function SplitPage() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("My weekly split");

  const { data: splits, isLoading, isError } = useQuery({
    queryKey: ["splits"],
    queryFn: fetchSplits,
  });
  const { data: exercises } = useQuery({ queryKey: ["exercises"], queryFn: fetchExercises });

  const start = useMutation({
    mutationFn: () => createSplit(name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["splits"] }),
  });

  const split = splits?.find((s) => s.is_active);
  const muscles = useMemo(() => {
    const set = new Set((exercises ?? []).map((e) => e.muscle_group).filter(Boolean));
    return [...set].sort();
  }, [exercises]);

  const byWeekday = useMemo(() => {
    const map = new Map<number, SplitDay>();
    split?.days.forEach((d) => map.set(d.weekday, d));
    return map;
  }, [split]);

  const today = todayWeekday();

  return (
    <div>
      <PageHeader
        title="My Split"
        subtitle="Plan your training week. Pick the muscles for each day, then the exercises."
      />

      {isLoading ? (
        <Card>
          <LoadingState />
        </Card>
      ) : isError ? (
        <Card>
          <ErrorState />
        </Card>
      ) : !split ? (
        <Card>
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            Set up your split
          </h2>
          <p className="mb-4 max-w-prose text-sm text-[var(--color-text-muted)]">
            Give your plan a name, then mark the days you train. Any day you don't add stays a
            rest day, so training four days a week just means adding four days.
          </p>
          <div className="flex flex-wrap gap-3">
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="max-w-xs"
              placeholder="Split name"
            />
            <Button onClick={() => start.mutate()} disabled={!name || start.isPending}>
              {start.isPending ? "Creating..." : "Create split"}
            </Button>
          </div>
        </Card>
      ) : (
        <>
          <div className="mb-5 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-display text-2xl text-[var(--color-text)]">{split.name}</h2>
            <p className="text-sm text-[var(--color-text-muted)]">
              {split.days_per_week} {split.days_per_week === 1 ? "day" : "days"} a week ·{" "}
              {split.days.reduce((n, d) => n + d.exercises.length, 0)} exercises planned
            </p>
          </div>

          {muscles.length === 0 && (
            <EmptyState>
              The exercise catalog is empty, so there are no muscles to pick from yet.
            </EmptyState>
          )}

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {WEEKDAYS.map((_, weekday) => (
              <DayCard
                key={weekday}
                weekday={weekday}
                day={byWeekday.get(weekday)}
                split={split}
                exercises={exercises ?? []}
                muscles={muscles}
                isToday={weekday === today}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
