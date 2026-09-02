import { useQuery } from "@tanstack/react-query";
import { fetchExercises } from "../api/workouts";
import MuscleLibrary from "../components/MuscleLibrary";
import { EmptyState, ErrorState, LoadingState, PageHeader } from "../components/ui";

export default function ExercisesPage() {
  const { data: exercises, isLoading, isError } = useQuery({ queryKey: ["exercises"], queryFn: fetchExercises });

  return (
    <div>
      <PageHeader
        title="Exercise Library"
        subtitle="Pick a muscle, drill into the region that needs work, and tap through to the form tutorial."
      />

      {isLoading ? (
        <LoadingState />
      ) : isError ? (
        <ErrorState />
      ) : exercises && exercises.length > 0 ? (
        <MuscleLibrary exercises={exercises} />
      ) : (
        <EmptyState>No exercises in the catalog yet.</EmptyState>
      )}
    </div>
  );
}
