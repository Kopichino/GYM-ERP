import { todayIso } from "../lib/dates";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  createGoal,
  deleteGoal,
  deleteMeasurement,
  fetchBodyStatsSummary,
  fetchGoals,
  fetchMeasurements,
  recordMeasurement,
  updateGoal,
  updateMyProfile,
  type BmiCategory,
  type GoalType,
  type MemberGoal,
} from "../api/bodystats";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  ErrorText,
  Input,
  LoadingState,
  Select, ghostButtonClass } from "./ui";
import { railColor } from "../lib/theme";

/** BMI bands share the app's status palette: green reads as healthy, amber as
 *  worth watching, red as the outer band. */
const BMI_COLOR: Record<BmiCategory, string> = {
  underweight: "#ffb020",
  normal: "#22c55e",
  overweight: "#ffb020",
  obese: "#ff3d5a",
};

const GOAL_TYPES: { value: GoalType; label: string; unit: string }[] = [
  { value: "weight", label: "Target weight", unit: "kg" },
  { value: "body_fat", label: "Target body fat", unit: "%" },
  { value: "attendance", label: "Monthly visits", unit: "visits" },
  { value: "custom", label: "Custom", unit: "" },
];

const unitFor = (t: GoalType) => GOAL_TYPES.find((g) => g.value === t)?.unit ?? "";

function Stat({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div>
      <p className="font-display text-3xl leading-none" style={{ color: color ?? "var(--color-text)" }}>
        {value}
      </p>
      <p className="mt-1 text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">{label}</p>
      {sub && <p className="text-xs text-[var(--color-text-muted)]">{sub}</p>}
    </div>
  );
}

function GoalRow({
  goal,
  onArchive,
  onDelete,
}: {
  goal: MemberGoal;
  onArchive: () => void;
  onDelete: () => void;
}) {
  const pct = goal.progress_pct === null ? null : Number(goal.progress_pct);
  const done = goal.status === "achieved";

  return (
    <li className="border-b border-[var(--color-border)] py-3 last:border-none">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-sm font-semibold text-[var(--color-text)]">{goal.label}</span>
        <span className="text-sm text-[var(--color-text-muted)]">
          {goal.live_value !== null ? `${goal.live_value} → ` : ""}
          {goal.target_value} {unitFor(goal.goal_type)}
        </span>
      </div>

      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-surface-2)]">
        <div
          className="h-full rounded-full transition-[width] duration-500"
          style={{
            width: `${pct ?? 0}%`,
            background: done ? "#22c55e" : "var(--color-accent)",
          }}
        />
      </div>

      <div className="mt-1.5 flex flex-wrap items-center gap-3 text-xs text-[var(--color-text-muted)]">
        <span>{pct === null ? "No data yet" : `${Math.round(pct)}% there`}</span>
        {goal.target_date && <span>by {new Date(goal.target_date).toLocaleDateString()}</span>}
        {done && <span style={{ color: "#22c55e" }}>Achieved</span>}
        <button onClick={onArchive} className="ml-auto hover:text-[var(--color-text)]">
          {goal.status === "archived" ? "Reactivate" : "Archive"}
        </button>
        <button onClick={onDelete} className={ghostButtonClass}>
          Delete
        </button>
      </div>
    </li>
  );
}

/**
 * Body composition and goals. Pass `memberId` to act on one of your assigned
 * members instead of yourself -- the API rejects anyone else's id.
 */
export default function BodyStatsPanel({ memberId }: { memberId?: number }) {
  const queryClient = useQueryClient();
  const onSelf = memberId === undefined;
  const key = ["bodystats", memberId ?? "me"];

  const { data: summary, isLoading, isError } = useQuery({
    queryKey: [...key, "summary"],
    queryFn: () => fetchBodyStatsSummary(memberId),
  });
  const { data: measurements } = useQuery({
    queryKey: [...key, "measurements"],
    queryFn: () => fetchMeasurements(memberId),
  });
  const { data: goals } = useQuery({
    queryKey: [...key, "goals"],
    queryFn: () => fetchGoals(memberId),
  });

  const [weight, setWeight] = useState("");
  const [bodyFat, setBodyFat] = useState("");
  const [height, setHeight] = useState("");
  const [goalType, setGoalType] = useState<GoalType>("weight");
  const [goalTitle, setGoalTitle] = useState("");
  const [goalTarget, setGoalTarget] = useState("");
  const [goalDate, setGoalDate] = useState("");
  const [error, setError] = useState("");

  const invalidate = () => queryClient.invalidateQueries({ queryKey: key });
  const fail = (fallback: string) => (err: { response?: { data?: Record<string, string[]> } }) => {
    const first = err.response?.data && Object.values(err.response.data)[0];
    setError(Array.isArray(first) ? first[0] : fallback);
  };

  const logWeight = useMutation({
    mutationFn: () =>
      recordMeasurement({
        weight_kg: weight,
        body_fat_pct: bodyFat || null,
        recorded_on: todayIso(),
        ...(memberId ? { user: memberId } : {}),
      }),
    onSuccess: () => {
      setWeight("");
      setBodyFat("");
      setError("");
      invalidate();
    },
    onError: fail("Could not save that weigh-in."),
  });

  const saveHeight = useMutation({
    mutationFn: () => updateMyProfile({ height_cm: Number(height) }),
    onSuccess: () => {
      setError("");
      invalidate();
      queryClient.invalidateQueries({ queryKey: ["me"] });
    },
    onError: fail("Could not save your height."),
  });

  const addGoal = useMutation({
    mutationFn: () =>
      createGoal({
        goal_type: goalType,
        title: goalTitle,
        // Today's reading is the baseline progress is measured from.
        start_value: goalType === "weight" ? summary?.weight_kg ?? null : null,
        target_value: goalTarget,
        target_date: goalDate || null,
        ...(memberId ? { user: memberId } : {}),
      }),
    onSuccess: () => {
      setGoalTitle("");
      setGoalTarget("");
      setGoalDate("");
      setError("");
      invalidate();
    },
    onError: fail("Could not create that goal."),
  });

  const changeGoal = useMutation({
    mutationFn: ({ id, status }: { id: number; status: MemberGoal["status"] }) =>
      updateGoal(id, { status }),
    onSuccess: invalidate,
  });
  const removeGoal = useMutation({ mutationFn: deleteGoal, onSuccess: invalidate });
  const removeMeasurement = useMutation({ mutationFn: deleteMeasurement, onSuccess: invalidate });

  if (isLoading) return <Card accent={railColor(0)}><LoadingState /></Card>;
  if (isError) return <Card accent={railColor(1)}><ErrorState /></Card>;

  const bmi = summary?.bmi ? Number(summary.bmi) : null;
  const band = summary?.bmi_category ?? null;
  const delta = summary?.change_since_previous ? Number(summary.change_since_previous) : null;
  const needsHeight = !summary?.height_cm;

  return (
    <div className="flex flex-col gap-6">
      <Card accent={railColor(2)}>
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Body stats
        </h2>

        {summary?.measurement_count === 0 ? (
          <EmptyState>No weigh-ins recorded yet. Add the first one below.</EmptyState>
        ) : (
          <div className="grid grid-cols-2 gap-5 sm:grid-cols-4">
            <Stat
              label="Weight"
              value={summary?.weight_kg ? `${Number(summary.weight_kg)}kg` : "--"}
              sub={summary?.recorded_on ? new Date(summary.recorded_on).toLocaleDateString() : undefined}
            />
            <Stat
              label="BMI"
              value={bmi !== null ? String(bmi) : "--"}
              sub={band ?? (needsHeight ? "Add height" : undefined)}
              color={band ? BMI_COLOR[band] : undefined}
            />
            <Stat
              label="Since last"
              value={delta === null ? "--" : `${delta > 0 ? "+" : ""}${delta}kg`}
              color={delta === null || delta === 0 ? undefined : delta < 0 ? "#22c55e" : "var(--color-accent-2)"}
            />
            <Stat
              label="Body fat"
              value={summary?.body_fat_pct ? `${Number(summary.body_fat_pct)}%` : "--"}
            />
          </div>
        )}

        {needsHeight && onSelf && (
          <div className="mt-5 flex flex-wrap items-end gap-3 border-t border-[var(--color-border)] pt-4">
            <label className="text-xs text-[var(--color-text-muted)]">
              Height (cm) — needed for BMI
              <Input
                type="number"
                min={50}
                max={300}
                value={height}
                onChange={(e) => setHeight(e.target.value)}
                className="mt-1 w-32"
                placeholder="175"
              />
            </label>
            <Button onClick={() => saveHeight.mutate()} disabled={!height || saveHeight.isPending}>
              {saveHeight.isPending ? "Saving..." : "Save height"}
            </Button>
          </div>
        )}
        {needsHeight && !onSelf && (
          <p className="mt-4 text-xs text-[var(--color-text-muted)]">
            BMI needs a height on this member's profile, which only they can set.
          </p>
        )}
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card accent={railColor(3)}>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            {onSelf ? "Log today's weigh-in" : "Record a weigh-in"}
          </h2>
          <div className="flex flex-wrap gap-3">
            <label className="flex-1 text-xs text-[var(--color-text-muted)]">
              Weight (kg)
              <Input
                type="number"
                step="0.1"
                min={1}
                value={weight}
                onChange={(e) => setWeight(e.target.value)}
                className="mt-1"
                placeholder="72.5"
              />
            </label>
            <label className="flex-1 text-xs text-[var(--color-text-muted)]">
              Body fat % (optional)
              <Input
                type="number"
                step="0.1"
                min={0}
                value={bodyFat}
                onChange={(e) => setBodyFat(e.target.value)}
                className="mt-1"
                placeholder="18.5"
              />
            </label>
          </div>
          <div className="mt-3 flex items-center gap-3">
            <Button onClick={() => logWeight.mutate()} disabled={!weight || logWeight.isPending}>
              {logWeight.isPending ? "Saving..." : "Save weigh-in"}
            </Button>
            <span className="text-xs text-[var(--color-text-muted)]">
              One per day — today's replaces itself.
            </span>
          </div>
          <ErrorText>{error}</ErrorText>

          <h3 className="mb-2 mt-6 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            Recent
          </h3>
          {!measurements?.length ? (
            <EmptyState>Nothing logged yet.</EmptyState>
          ) : (
            <ul className="flex flex-col">
              {measurements.slice(0, 6).map((m) => (
                <li
                  key={m.id}
                  className="flex items-center justify-between gap-3 border-b border-[var(--color-border)] py-2 text-sm last:border-none"
                >
                  <span className="text-[var(--color-text-muted)]">
                    {new Date(m.recorded_on).toLocaleDateString()}
                  </span>
                  <span className="text-[var(--color-text)]">
                    {Number(m.weight_kg)}kg
                    {m.bmi && (
                      <span className="ml-2 text-[var(--color-text-muted)]">BMI {Number(m.bmi)}</span>
                    )}
                    {m.recorded_by_name && (
                      <span className="ml-2 text-xs text-[var(--color-text-muted)]">
                        by {m.recorded_by_name}
                      </span>
                    )}
                  </span>
                  <button
                    onClick={() => removeMeasurement.mutate(m.id)}
                    className={ghostButtonClass}
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card accent={railColor(4)}>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            Goals
          </h2>

          {!goals?.length ? (
            <EmptyState>No goals set yet.</EmptyState>
          ) : (
            <ul className="mb-5 flex flex-col">
              {goals.map((g) => (
                <GoalRow
                  key={g.id}
                  goal={g}
                  onArchive={() =>
                    changeGoal.mutate({
                      id: g.id,
                      status: g.status === "archived" ? "active" : "archived",
                    })
                  }
                  onDelete={() => removeGoal.mutate(g.id)}
                />
              ))}
            </ul>
          )}

          <div className="border-t border-[var(--color-border)] pt-4">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              Add a goal
            </h3>
            <div className="flex flex-col gap-3">
              <Select value={goalType} onChange={(e) => setGoalType(e.target.value as GoalType)}>
                {GOAL_TYPES.map((g) => (
                  <option key={g.value} value={g.value}>
                    {g.label}
                  </option>
                ))}
              </Select>
              {goalType === "custom" && (
                <Input
                  placeholder="What are you working toward?"
                  value={goalTitle}
                  onChange={(e) => setGoalTitle(e.target.value)}
                />
              )}
              <div className="flex gap-3">
                <label className="flex-1 text-xs text-[var(--color-text-muted)]">
                  Target {unitFor(goalType) && `(${unitFor(goalType)})`}
                  <Input
                    type="number"
                    step="0.1"
                    value={goalTarget}
                    onChange={(e) => setGoalTarget(e.target.value)}
                    className="mt-1"
                  />
                </label>
                <label className="flex-1 text-xs text-[var(--color-text-muted)]">
                  By (optional)
                  <Input
                    type="date"
                    value={goalDate}
                    onChange={(e) => setGoalDate(e.target.value)}
                    className="mt-1"
                  />
                </label>
              </div>
              <Button
                onClick={() => addGoal.mutate()}
                disabled={!goalTarget || addGoal.isPending}
              >
                {addGoal.isPending ? "Adding..." : "Add goal"}
              </Button>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
