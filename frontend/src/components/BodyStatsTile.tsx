import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchBodyStatsSummary, fetchGoals, type BmiCategory } from "../api/bodystats";
import { Card } from "./ui";

const BMI_COLOR: Record<BmiCategory, string> = {
  underweight: "#ffb020",
  normal: "#22c55e",
  overweight: "#ffb020",
  obese: "#ff3d5a",
};

/** Compact dashboard read-out: latest weight, BMI and the nearest active goal.
 *  Logging and goal-setting live on the profile page. */
export default function BodyStatsTile() {
  const { data: summary } = useQuery({
    queryKey: ["bodystats", "me", "summary"],
    queryFn: () => fetchBodyStatsSummary(),
  });
  const { data: goals } = useQuery({
    queryKey: ["bodystats", "me", "goals"],
    queryFn: () => fetchGoals(),
  });

  const activeGoal = goals?.find((g) => g.status === "active");
  const pct = activeGoal?.progress_pct === null || activeGoal === undefined
    ? null
    : Number(activeGoal.progress_pct);
  const band = summary?.bmi_category ?? null;
  const delta = summary?.change_since_previous ? Number(summary.change_since_previous) : null;

  return (
    <Card accent={"#22c55e"}>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Body stats
        </h2>
        <Link
          to="/profile"
          className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-accent)]"
        >
          {summary?.measurement_count ? "Update" : "Get started"}
        </Link>
      </div>

      {!summary?.measurement_count ? (
        <p className="text-sm text-[var(--color-text-muted)]">
          Log a weigh-in on your{" "}
          <Link to="/profile" className="text-[var(--color-accent)] hover:underline">
            profile
          </Link>{" "}
          to track BMI and goals.
        </p>
      ) : (
        <>
          <div className="flex items-end gap-6">
            <div>
              <p className="font-display text-3xl leading-none text-[var(--color-text)]">
                {Number(summary.weight_kg)}kg
              </p>
              <p className="mt-1 text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">
                {delta === null || delta === 0
                  ? "Latest weight"
                  : `${delta > 0 ? "+" : ""}${delta}kg since last`}
              </p>
            </div>
            <div>
              <p
                className="font-display text-3xl leading-none"
                style={{ color: band ? BMI_COLOR[band] : "var(--color-text)" }}
              >
                {summary.bmi ? Number(summary.bmi) : "--"}
              </p>
              <p className="mt-1 text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">
                {band ?? "Add height for BMI"}
              </p>
            </div>
          </div>

          {activeGoal && (
            <div className="mt-4 border-t border-[var(--color-border)] pt-3">
              <div className="flex items-baseline justify-between gap-2 text-sm">
                <span className="text-[var(--color-text)]">{activeGoal.label}</span>
                <span className="text-[var(--color-text-muted)]">
                  {pct === null ? "No data" : `${Math.round(pct)}%`}
                </span>
              </div>
              <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-surface-2)]">
                <div
                  className="h-full rounded-full bg-[var(--color-accent)] transition-[width] duration-500"
                  style={{ width: `${pct ?? 0}%` }}
                />
              </div>
            </div>
          )}
        </>
      )}
    </Card>
  );
}
