import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { addLog, createSession, fetchExercises, fetchSessions } from "../api/workouts";
import { Button, Card, ErrorState, LoadingState, PageHeader, Select } from "../components/ui";
import VideoStrip from "../components/VideoStrip";

export default function WorkoutsPage() {
  const queryClient = useQueryClient();
  const { data: exercises } = useQuery({ queryKey: ["exercises"], queryFn: fetchExercises });
  const { data: sessions, isLoading: sessionsLoading, isError: sessionsError } = useQuery({
    queryKey: ["sessions"],
    queryFn: fetchSessions,
  });

  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [exerciseId, setExerciseId] = useState<number | "">("");
  const [reps, setReps] = useState(10);
  const [weight, setWeight] = useState(0);
  const [unit, setUnit] = useState<"kg" | "lb">("kg");

  const startSession = useMutation({
    mutationFn: () => createSession(""),
    onSuccess: (session) => {
      setActiveSessionId(session.id);
      queryClient.invalidateQueries({ queryKey: ["sessions"] });
    },
  });

  const selectedExercise = exercises?.find((ex) => ex.id === exerciseId);
  const activeSession = sessions?.find((s) => s.id === activeSessionId) ?? sessions?.[0];
  const nextSetNumber = (activeSession?.logs.filter((l) => l.exercise === exerciseId).length ?? 0) + 1;

  const logSet = useMutation({
    mutationFn: () => {
      if (!activeSession || !exerciseId) throw new Error("missing session/exercise");
      return addLog({
        session: activeSession.id,
        exercise: exerciseId,
        set_number: nextSetNumber,
        reps,
        weight,
        weight_unit: unit,
      });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sessions"] }),
  });

  return (
    <div>
      <PageHeader title="Workout Logger" subtitle="Track your sets, reps, and weight for each session." />

      {sessionsLoading ? (
        <Card>
          <LoadingState label="Loading your sessions..." />
        </Card>
      ) : sessionsError ? (
        <Card>
          <ErrorState />
        </Card>
      ) : !activeSession ? (
        <Card>
          <p className="mb-4 text-sm text-[var(--color-text-muted)]">
            Start today's session to begin logging sets.
          </p>
          <Button onClick={() => startSession.mutate()} disabled={startSession.isPending}>
            {startSession.isPending ? "Starting..." : "Start Today's Session"}
          </Button>
        </Card>
      ) : (
        <div className="grid gap-6 md:grid-cols-2">
          <Card>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              Log a set -- session {new Date(activeSession.date).toLocaleDateString()}
            </h2>
            <div className="flex flex-col gap-3">
              <Select value={exerciseId} onChange={(e) => setExerciseId(Number(e.target.value) || "")}>
                <option value="">Select exercise</option>
                {exercises?.map((ex) => (
                  <option key={ex.id} value={ex.id}>
                    {ex.name}
                  </option>
                ))}
              </Select>
              {selectedExercise && (
                <div>
                  <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                    Form tutorials
                  </p>
                  <VideoStrip videos={selectedExercise.videos} />
                </div>
              )}
              <div className="flex gap-3">
                <label className="flex-1 text-xs text-[var(--color-text-muted)]">
                  Reps
                  <input
                    type="number"
                    min={1}
                    value={reps}
                    onChange={(e) => setReps(Number(e.target.value))}
                    className="mt-1 w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm text-[var(--color-text)]"
                  />
                </label>
                <label className="flex-1 text-xs text-[var(--color-text-muted)]">
                  Weight
                  <input
                    type="number"
                    min={0}
                    step="0.5"
                    value={weight}
                    onChange={(e) => setWeight(Number(e.target.value))}
                    className="mt-1 w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm text-[var(--color-text)]"
                  />
                </label>
                <label className="w-20 text-xs text-[var(--color-text-muted)]">
                  Unit
                  <Select value={unit} onChange={(e) => setUnit(e.target.value as "kg" | "lb")} className="mt-1">
                    <option value="kg">kg</option>
                    <option value="lb">lb</option>
                  </Select>
                </label>
              </div>
              <Button
                onClick={() => logSet.mutate()}
                disabled={!exerciseId || logSet.isPending}
              >
                {logSet.isPending ? "Logging..." : `Log Set ${nextSetNumber}`}
              </Button>
            </div>
          </Card>

          <Card>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              This session's sets
            </h2>
            <ul className="flex flex-col gap-2">
              {activeSession.logs.map((log) => (
                <li
                  key={log.id}
                  className="flex items-center justify-between border-b border-[var(--color-border)] py-2 text-sm last:border-none"
                >
                  <span className="text-[var(--color-text)]">{log.exercise_name}</span>
                  <span className="text-[var(--color-text-muted)]">
                    Set {log.set_number}: {log.reps} x {log.weight}
                    {log.weight_unit}
                  </span>
                </li>
              ))}
              {activeSession.logs.length === 0 && (
                <p className="text-sm text-[var(--color-text-muted)]">No sets logged yet.</p>
              )}
            </ul>
          </Card>
        </div>
      )}
    </div>
  );
}
