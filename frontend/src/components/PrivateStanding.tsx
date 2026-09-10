import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fetchStanding } from "../api/gamification";
import { fetchExercises } from "../api/workouts";
import { railColor } from "../lib/theme";
import { Card, EmptyState, LoadingState, Select } from "./ui";

/**
 * "Just for me" — where the member sits, without going on the public board.
 *
 * The whole point of this panel is that opting out of the leaderboard should
 * cost a member the *exposure*, not the feedback. Nothing here names anyone
 * else, and the server refuses to place anybody at all when the pool is small
 * enough that a percentile would give people away.
 */
export default function PrivateStanding() {
  const [exerciseId, setExerciseId] = useState<number | "">("");

  const { data: exercises } = useQuery({ queryKey: ["exercises"], queryFn: fetchExercises });
  const { data, isLoading } = useQuery({
    queryKey: ["standing", exerciseId],
    queryFn: () => fetchStanding(exerciseId as number),
    enabled: exerciseId !== "",
  });

  const placed = data && data.top_percent !== null;

  // Three framings of one rank, because the same fact reads very differently
  // depending on where in the pool it falls. "Top 20%" is the phrase people
  // actually use; "top 80%" is a put-down for the identical number, so the
  // bottom half is told what it is ahead of instead. Last place is ahead of
  // nobody, and "ahead of 0%" is worse than simply saying the position.
  const headline = !placed
    ? ""
    : data.top_percent! <= 50
      ? `Top ${data.top_percent}%`
      : data.better_than! > 0
        ? `Ahead of ${data.better_than}%`
        : `#${data.rank} of ${data.pool}`;
  const headlineIsRank = placed && data.better_than === 0;

  return (
    <Card accent={railColor(4)}>
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Just for you
        </h2>
        <Select
          value={exerciseId}
          onChange={(e) => setExerciseId(Number(e.target.value) || "")}
          className="max-w-[220px]"
        >
          <option value="">Pick a lift</option>
          {exercises?.map((ex) => (
            <option key={ex.id} value={ex.id}>
              {ex.name}
            </option>
          ))}
        </Select>
      </div>
      <p className="mb-4 max-w-prose text-sm text-[var(--color-text-muted)]">
        Where you sit this month, shown only to you. You do not have to be on the public board
        for this, and it never tells you who anyone else is.
      </p>

      {exerciseId === "" ? (
        <EmptyState>Pick a lift to see where you stand.</EmptyState>
      ) : isLoading || !data ? (
        <LoadingState />
      ) : placed ? (
        <div className="flex flex-wrap items-end gap-6">
          <div>
            <p
              className="font-display text-5xl leading-none"
              style={{ color: railColor(4) }}
            >
              {headline}
            </p>
            <p className="mt-1 text-xs uppercase tracking-wide text-[var(--color-text-muted)]">
              of the {data.pool} members lifting this
            </p>
          </div>
          {/* Skipped when the headline is already the rank. */}
          {!headlineIsRank && (
            <div>
              <p className="font-display text-3xl leading-none text-[var(--color-text)]">
                #{data.rank}
              </p>
              <p className="mt-1 text-xs uppercase tracking-wide text-[var(--color-text-muted)]">
                your position
              </p>
            </div>
          )}
          <div>
            <p className="font-display text-3xl leading-none text-[var(--color-text)]">
              {Number(data.ratio).toFixed(2)}×
            </p>
            <p className="mt-1 text-xs uppercase tracking-wide text-[var(--color-text-muted)]">
              your bodyweight
            </p>
          </div>
        </div>
      ) : (
        <EmptyState>{data.reason}</EmptyState>
      )}
    </Card>
  );
}
