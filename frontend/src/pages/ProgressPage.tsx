import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fetchExercises, fetchProgress } from "../api/workouts";
import ProgressChart from "../components/ProgressChart";
import { Card, ErrorState, LoadingState, PageHeader, Select } from "../components/ui";

export default function ProgressPage() {
  const { data: exercises, isLoading: exercisesLoading, isError: exercisesError } = useQuery({
    queryKey: ["exercises"],
    queryFn: fetchExercises,
  });
  const [exerciseId, setExerciseId] = useState<number | "">("");

  const { data: progress, isLoading: progressLoading, isError: progressError } = useQuery({
    queryKey: ["progress", exerciseId],
    queryFn: () => fetchProgress(exerciseId as number),
    enabled: exerciseId !== "",
  });

  return (
    <div>
      <PageHeader
        title="Progress Tracker"
        subtitle="How your lifts trend, and what the rest of the week looks like."
      />
      <Card className="mb-6">
        {exercisesLoading ? (
          <LoadingState label="Loading exercises..." />
        ) : exercisesError ? (
          <ErrorState />
        ) : (
          <Select
            value={exerciseId}
            onChange={(e) => setExerciseId(Number(e.target.value) || "")}
            className="mb-6 max-w-xs"
          >
            <option value="">Select an exercise</option>
            {exercises?.map((ex) => (
              <option key={ex.id} value={ex.id}>
                {ex.name}
              </option>
            ))}
          </Select>
        )}

        {exerciseId === "" ? (
          <p className="text-sm text-[var(--color-text-muted)]">Pick an exercise to see its trend.</p>
        ) : progressLoading ? (
          <LoadingState label="Loading progress..." />
        ) : progressError ? (
          <ErrorState />
        ) : !progress?.length ? (
          <p className="text-sm text-[var(--color-text-muted)]">No logged sets for this exercise yet.</p>
        ) : (
          <ProgressChart points={progress} />
        )}
      </Card>
    </div>
  );
}
