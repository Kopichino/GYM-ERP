import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { addLog, createSession, fetchExercises, fetchProgress, fetchSessions } from "../../api/workouts";
import { fetchMyMember, type TrainerMember } from "../../api/users";
import BodyStatsPanel from "../../components/BodyStatsPanel";
import DietPlanner from "../../components/DietPlanner";
import ProgressChart from "../../components/ProgressChart";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Select,
} from "../../components/ui";
import { railColor } from "../../lib/theme";

/** Answers that mean "not one of your members" -- final, not worth retrying. */
const NOT_YOURS = [403, 404];

function statusOf(error: unknown) {
  return (error as { response?: { status?: number } } | null)?.response?.status ?? 0;
}

function BackToMembers() {
  return (
    <Link
      to="/trainer/members"
      className="mb-4 inline-block text-sm text-[var(--color-text-muted)] hover:text-[var(--color-accent)]"
    >
      &#8249; Back to my members
    </Link>
  );
}

/**
 * A trainer's page for one member.
 *
 * The member is looked up first, and nothing member-specific is shown until they
 * come back. The page used to take the id straight from the URL and render the
 * workout logger, body stats and diet planner for any number at all -- a member
 * that did not exist, or was someone else's, got a working-looking form whose
 * every save the server then refused.
 */
export default function TrainerMemberDetailPage() {
  const { memberId } = useParams();
  const id = Number(memberId);
  // An id that cannot belong to anyone is not asked about at all.
  const validId = Number.isInteger(id) && id > 0;

  const { data: member, isLoading, error } = useQuery({
    queryKey: ["trainer", "members", id],
    queryFn: () => fetchMyMember(id),
    enabled: validId,
    retry: (failures, err) => !NOT_YOURS.includes(statusOf(err)) && failures < 1,
  });

  if (!validId || NOT_YOURS.includes(statusOf(error))) {
    return (
      <div>
        <PageHeader title="Member not found" subtitle="Nothing to log here." />
        <BackToMembers />
        <Card accent={railColor(1)}>
          <EmptyState>
            We couldn&apos;t find that member among the members assigned to you. They may have been
            moved to another trainer, or the link may be wrong.
          </EmptyState>
        </Card>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div>
        <PageHeader title="Member" subtitle="Log sessions and track this member's progress." />
        <BackToMembers />
        <Card accent={railColor(0)}>
          <LoadingState />
        </Card>
      </div>
    );
  }

  if (error || !member) {
    return (
      <div>
        <PageHeader title="Member" subtitle="Log sessions and track this member's progress." />
        <BackToMembers />
        <Card accent={railColor(1)}>
          <ErrorState />
        </Card>
      </div>
    );
  }

  return <MemberWorkspace member={member} />;
}

/** Everything a trainer does for one confirmed member. Mounted only once the
 *  member has been found, so none of its reads or writes can go to anyone else. */
function MemberWorkspace({ member }: { member: TrainerMember }) {
  const id = member.id;
  const queryClient = useQueryClient();

  const { data: exercises } = useQuery({ queryKey: ["exercises"], queryFn: fetchExercises });
  const { data: sessions, isLoading, isError } = useQuery({
    queryKey: ["sessions", id],
    queryFn: () => fetchSessions(id),
  });

  const [exerciseId, setExerciseId] = useState<number | "">("");
  const [reps, setReps] = useState(10);
  const [weight, setWeight] = useState(0);
  const [unit, setUnit] = useState<"kg" | "lb">("kg");
  const [chartExerciseId, setChartExerciseId] = useState<number | "">("");

  const { data: progress, isLoading: progressLoading } = useQuery({
    queryKey: ["progress", chartExerciseId, id],
    queryFn: () => fetchProgress(chartExerciseId as number, id),
    enabled: chartExerciseId !== "",
  });

  const activeSession = sessions?.[0];
  const nextSetNumber =
    (activeSession?.logs.filter((l) => l.exercise === exerciseId).length ?? 0) + 1;

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["sessions", id] });
    queryClient.invalidateQueries({ queryKey: ["progress"] });
  }

  const startSession = useMutation({
    mutationFn: () => createSession("", id),
    onSuccess: invalidate,
  });

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
    onSuccess: invalidate,
  });

  const displayName = `${member.first_name} ${member.last_name}`.trim() || member.username;

  return (
    <div>
      <PageHeader title={displayName} subtitle="Log sessions and track this member's progress." />
      <BackToMembers />

      {isLoading ? (
        <Card accent={railColor(0)}>
          <LoadingState />
        </Card>
      ) : isError ? (
        <Card accent={railColor(1)}>
          <ErrorState />
        </Card>
      ) : (
        // One column below `md` is stated, not left implicit: an implicit
        // column is as wide as its widest item's minimum, and the diet
        // planner's week strip -- seven 104px day cards, built to scroll
        // sideways -- made that 776px, pushing every card off a phone.
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          <Card accent={railColor(2)}>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              Log a set
            </h2>
            {!activeSession ? (
              <>
                <p className="mb-4 text-sm text-[var(--color-text-muted)]">
                  No session yet for this member.
                </p>
                <Button onClick={() => startSession.mutate()} disabled={startSession.isPending}>
                  {startSession.isPending ? "Starting..." : "Start a session"}
                </Button>
              </>
            ) : (
              <div className="flex flex-col gap-3">
                <p className="text-xs text-[var(--color-text-muted)]">
                  Session {new Date(activeSession.date).toLocaleDateString()}
                </p>
                <Select
                  value={exerciseId}
                  onChange={(e) => setExerciseId(Number(e.target.value) || "")}
                >
                  <option value="">Select exercise</option>
                  {exercises?.map((ex) => (
                    <option key={ex.id} value={ex.id}>
                      {ex.name}
                    </option>
                  ))}
                </Select>
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
                    <Select
                      value={unit}
                      onChange={(e) => setUnit(e.target.value as "kg" | "lb")}
                      className="mt-1"
                    >
                      <option value="kg">kg</option>
                      <option value="lb">lb</option>
                    </Select>
                  </label>
                </div>
                <Button onClick={() => logSet.mutate()} disabled={!exerciseId || logSet.isPending}>
                  {logSet.isPending ? "Logging..." : `Log Set ${nextSetNumber}`}
                </Button>
              </div>
            )}
          </Card>

          <Card accent={railColor(3)}>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              This session's sets
            </h2>
            <ul className="flex flex-col gap-2">
              {activeSession?.logs.map((log) => (
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
              {!activeSession?.logs.length && <EmptyState>No sets logged yet.</EmptyState>}
            </ul>
          </Card>

          <div className="md:col-span-2">
            <BodyStatsPanel memberId={id} />
          </div>

          <Card accent={railColor(4)} className="md:col-span-2">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              Lifting progress
            </h2>
            <Select
              value={chartExerciseId}
              onChange={(e) => setChartExerciseId(Number(e.target.value) || "")}
              className="mb-6 max-w-xs"
            >
              <option value="">Select an exercise</option>
              {exercises?.map((ex) => (
                <option key={ex.id} value={ex.id}>
                  {ex.name}
                </option>
              ))}
            </Select>
            {chartExerciseId === "" ? (
              <p className="text-sm text-[var(--color-text-muted)]">
                Pick an exercise to see the trend.
              </p>
            ) : progressLoading ? (
              <LoadingState label="Loading progress..." />
            ) : !progress?.length ? (
              <p className="text-sm text-[var(--color-text-muted)]">
                No logged sets for this exercise yet.
              </p>
            ) : (
              <ProgressChart points={progress} />
            )}
          </Card>

          {/* Not wrapped in a Card: the planner brings its own, and nesting
              them boxed every meal inside two borders. */}
          <div className="md:col-span-2">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              Diet plan
            </h2>
            {/* Same planner the member uses, pointed at them -- so a plan a
                trainer writes and one a member writes are the same object. */}
            <DietPlanner member={id} />
          </div>
        </div>
      )}
    </div>
  );
}
