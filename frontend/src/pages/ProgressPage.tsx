import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fetchExercises, fetchProgress } from "../api/workouts";
import { Card, PageHeader, Select } from "../components/ui";

export default function ProgressPage() {
  const { data: exercises } = useQuery({ queryKey: ["exercises"], queryFn: fetchExercises });
  const [exerciseId, setExerciseId] = useState<number | "">("");

  const { data: progress } = useQuery({
    queryKey: ["progress", exerciseId],
    queryFn: () => fetchProgress(exerciseId as number),
    enabled: exerciseId !== "",
  });

  const chartData =
    progress?.map((p) => ({
      date: new Date(p.session__date).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
      maxWeight: Number(p.max_weight),
      totalReps: p.total_reps,
    })) ?? [];

  return (
    <div>
      <PageHeader title="Progress Tracker" subtitle="See how your lifts trend over time." />
      <Card>
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

        {exerciseId === "" ? (
          <p className="text-sm text-[var(--color-text-muted)]">Pick an exercise to see its trend.</p>
        ) : chartData.length === 0 ? (
          <p className="text-sm text-[var(--color-text-muted)]">No logged sets for this exercise yet.</p>
        ) : (
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" />
                <XAxis dataKey="date" stroke="var(--color-text-muted)" fontSize={12} />
                <YAxis stroke="var(--color-text-muted)" fontSize={12} />
                <Tooltip
                  contentStyle={{
                    background: "var(--color-surface-2)",
                    border: "1px solid var(--color-border)",
                    borderRadius: 8,
                    color: "var(--color-text)",
                  }}
                />
                <Line type="monotone" dataKey="maxWeight" name="Max weight" stroke="var(--color-accent)" strokeWidth={2} />
                <Line type="monotone" dataKey="totalReps" name="Total reps" stroke="var(--color-accent-2)" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>
    </div>
  );
}
