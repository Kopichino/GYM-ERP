import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useMemo, useState } from "react";
import {
  fetchAchievements,
  fetchLeaderboard,
  fetchMyRecords,
  setLeaderboardOptIn,
  TIER_COLOURS,
  type BadgeProgress,
  type Tier,
} from "../api/gamification";
import { fetchExercises } from "../api/workouts";
import BadgeMedal from "../components/BadgeMedal";
import PrivateStanding from "../components/PrivateStanding";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Select,
  tableCellClass,
  tableHeadCellClass,
  tableHeadRowClass,
  tableRowClass,
} from "../components/ui";
import { fadeUp, staggerContainer } from "../lib/motion";
import { railColor } from "../lib/theme";
import { useAuthStore } from "../store/authStore";

function BadgeCard({ row }: { row: BadgeProgress }) {
  const colour = TIER_COLOURS[row.badge.tier as Tier];
  return (
    <motion.div
      variants={fadeUp}
      className="relative flex gap-3 overflow-hidden rounded-xl border p-3"
      style={{
        borderColor: row.earned ? colour : "var(--color-border)",
        background: row.earned
          ? `linear-gradient(135deg, ${colour}1a, var(--color-surface))`
          : "var(--color-surface)",
      }}
    >
      <BadgeMedal badge={row.badge} earned={row.earned} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-[var(--color-text)]">
          {row.badge.name}
        </p>
        <p className="text-[11px] uppercase tracking-wide" style={{ color: colour }}>
          {row.badge.tier_name}
        </p>

        {row.earned ? (
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">
            Earned {row.awarded_on ? new Date(row.awarded_on).toLocaleDateString() : ""}
          </p>
        ) : (
          <>
            <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-surface-2)]">
              <div
                className="h-full rounded-full transition-[width] duration-500"
                style={{ width: `${row.percent}%`, background: colour }}
              />
            </div>
            <p className="mt-1 text-xs tabular-nums text-[var(--color-text-muted)]">
              {/* A lift badge names its exercise instead of the generic
                  criterion: "80 / 100 kg · Barbell Bench Press" tells a member
                  what to go and do, where "heaviest lift on one exercise"
                  reads the same on every one of them. */}
              {row.badge.criterion === "lift"
                ? `${row.value} / ${row.threshold} kg · ${row.badge.exercise_name}`
                : `${row.value} / ${row.threshold} · ${row.badge.criterion_name.toLowerCase()}`}
            </p>
          </>
        )}
      </div>
    </motion.div>
  );
}

/** Ranked on weight lifted per kilo of bodyweight, taken at the time of the lift. */
function Leaderboard({ optedIn }: { optedIn: boolean }) {
  const [exerciseId, setExerciseId] = useState<number | "">("");
  const me = useAuthStore((s) => s.user);

  const { data: exercises } = useQuery({ queryKey: ["exercises"], queryFn: fetchExercises });
  const { data, isLoading } = useQuery({
    queryKey: ["leaderboard", exerciseId],
    queryFn: () => fetchLeaderboard(exerciseId === "" ? undefined : Number(exerciseId)),
  });

  const month = data
    ? new Date(data.month_start).toLocaleDateString(undefined, {
        month: "long",
        year: "numeric",
      })
    : "";

  return (
    <Card accent={railColor(2)}>
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Leaderboard — {month}
        </h2>
        <Select
          value={exerciseId}
          onChange={(e) => setExerciseId(Number(e.target.value) || "")}
          className="max-w-[220px]"
        >
          <option value="">Every exercise</option>
          {exercises?.map((ex) => (
            <option key={ex.id} value={ex.id}>
              {ex.name}
            </option>
          ))}
        </Select>
      </div>
      <p className="mb-4 max-w-prose text-sm text-[var(--color-text-muted)]">
        Scored on weight lifted per kilo of your own bodyweight, using what you weighed on the
        day — so a lighter lifter can out-rank a heavier one, and losing weight later never
        changes an old lift. Resets at the start of each month.
      </p>

      {!optedIn && (
        <p className="mb-4 rounded-md bg-[var(--color-surface-2)] p-3 text-sm text-[var(--color-text-muted)]">
          You are not on the board. Opt in above to appear — you can still see everyone else
          either way.
        </p>
      )}

      {isLoading ? (
        <LoadingState />
      ) : !data?.results.length ? (
        <EmptyState>
          Nobody has set a record this month yet. Log a heavy set and you will be first.
        </EmptyState>
      ) : (
        <div className="no-scrollbar overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-[var(--color-text-muted)]">
              <tr className={tableHeadRowClass}>
                <th className={tableHeadCellClass}>#</th>
                <th className={tableHeadCellClass}>Member</th>
                <th className={tableHeadCellClass}>Exercise</th>
                <th className={tableHeadCellClass}>Lifted</th>
                <th className={tableHeadCellClass}>Bodyweight</th>
                <th className={tableHeadCellClass}>Ratio</th>
              </tr>
            </thead>
            <tbody>
              {data.results.map((row) => {
                const isMe = row.member_id === me?.id;
                return (
                  <tr
                    key={`${row.member_id}-${row.exercise_id}`}
                    className={tableRowClass}
                    style={isMe ? { background: "var(--color-surface-2)" } : undefined}
                  >
                    <td className={`${tableCellClass} tabular-nums`}>{row.rank}</td>
                    <td className={tableCellClass}>
                      {row.full_name || row.username}
                      {isMe && (
                        <span className="ml-2 text-[10px] uppercase tracking-wide text-[var(--color-accent)]">
                          you
                        </span>
                      )}
                    </td>
                    <td className={tableCellClass}>{row.exercise}</td>
                    <td className={`${tableCellClass} tabular-nums`}>
                      {Math.round(Number(row.weight_kg))}kg × {row.reps}
                    </td>
                    <td className={`${tableCellClass} tabular-nums text-[var(--color-text-muted)]`}>
                      {Math.round(Number(row.bodyweight_kg))}kg
                    </td>
                    <td className={`${tableCellClass} tabular-nums font-semibold`}>
                      {row.ratio}×
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

export default function AchievementsPage() {
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["achievements"],
    queryFn: fetchAchievements,
  });
  const { data: records } = useQuery({ queryKey: ["my-records"], queryFn: fetchMyRecords });

  const optIn = useMutation({
    mutationFn: (next: boolean) => setLeaderboardOptIn(next),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["achievements"] });
      queryClient.invalidateQueries({ queryKey: ["leaderboard"] });
    },
  });

  // Best ratio first: the member's strongest lift relative to themselves is
  // the one they will want at the top, not whichever is alphabetically first.
  const sortedRecords = useMemo(
    () =>
      [...(records ?? [])].sort(
        (a, b) => Number(b.ratio ?? 0) - Number(a.ratio ?? 0)
      ),
    [records]
  );

  if (isLoading) {
    return (
      <div>
        <PageHeader title="Achievements" />
        <Card>
          <LoadingState />
        </Card>
      </div>
    );
  }
  if (isError || !data) {
    return (
      <div>
        <PageHeader title="Achievements" />
        <Card>
          <ErrorState />
        </Card>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Achievements"
        subtitle="Streaks, badges and your personal records."
      />

      {data.newly_awarded.length > 0 && (
        <Card accent="#ffb020" className="mb-6">
          <p className="font-display text-2xl uppercase tracking-wide text-[var(--color-text)]">
            {data.newly_awarded.length === 1
              ? "New badge unlocked"
              : `${data.newly_awarded.length} new badges unlocked`}
          </p>
          <p className="mt-1 text-sm text-[var(--color-text-muted)]">
            Have a look below — they are the ones with a glow.
          </p>
        </Card>
      )}

      <div className="mb-6 grid gap-6 sm:grid-cols-3">
        <Card accent={railColor(0)}>
          <p className="font-display text-4xl leading-none text-[var(--color-accent)]">
            {data.current_streak}
          </p>
          <p className="mt-1 text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">
            Day streak · best {data.longest_streak}
          </p>
        </Card>
        <Card accent={railColor(1)}>
          <p className="font-display text-4xl leading-none text-[var(--color-text)]">
            {data.total_visits}
          </p>
          <p className="mt-1 text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">
            Total visits
          </p>
        </Card>
        <Card accent={railColor(3)}>
          <p className="font-display text-4xl leading-none text-[var(--color-text)]">
            {data.earned_count}
            <span className="text-2xl text-[var(--color-text-muted)]">/{data.badge_count}</span>
          </p>
          <p className="mt-1 text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">
            Badges earned
          </p>
        </Card>
      </div>

      <Card accent={railColor(4)} className="mb-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            Badges
          </h2>
          <span className="flex items-center gap-3">
            <span className="text-xs text-[var(--color-text-muted)]">
              {data.leaderboard_opt_in ? "You're on the leaderboard" : "Leaderboard: private"}
            </span>
            <Button
              variant="secondary"
              onClick={() => optIn.mutate(!data.leaderboard_opt_in)}
              disabled={optIn.isPending}
              className="px-3 py-1 text-xs"
            >
              {data.leaderboard_opt_in ? "Leave the board" : "Join the board"}
            </Button>
          </span>
        </div>

        {!data.badges.length ? (
          <EmptyState>No badges have been set up yet.</EmptyState>
        ) : (
          <motion.div
            initial="hidden"
            animate="visible"
            variants={staggerContainer(0.03)}
            className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
          >
            {data.badges.map((row) => (
              <BadgeCard key={row.badge.id} row={row} />
            ))}
          </motion.div>
        )}
      </Card>

      <Card accent={railColor(5)} className="mb-6">
        <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Your records
        </h2>
        <p className="mb-4 text-sm text-[var(--color-text-muted)]">
          Read from your workout log — you never enter these. The bodyweight shown is what you
          weighed on the day of the lift.
        </p>
        {!sortedRecords.length ? (
          <EmptyState>
            No records yet. Log a set with a weight against it and one will appear.
          </EmptyState>
        ) : (
          <div className="no-scrollbar overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-[var(--color-text-muted)]">
                <tr className={tableHeadRowClass}>
                  <th className={tableHeadCellClass}>Exercise</th>
                  <th className={tableHeadCellClass}>Lifted</th>
                  <th className={tableHeadCellClass}>Bodyweight then</th>
                  <th className={tableHeadCellClass}>Ratio</th>
                  <th className={tableHeadCellClass}>When</th>
                </tr>
              </thead>
              <tbody>
                {sortedRecords.map((record) => (
                  <tr key={record.id} className={tableRowClass}>
                    <td className={tableCellClass}>{record.exercise_name}</td>
                    <td className={`${tableCellClass} tabular-nums`}>
                      {Math.round(Number(record.weight_kg))}kg × {record.reps}
                    </td>
                    <td className={`${tableCellClass} tabular-nums text-[var(--color-text-muted)]`}>
                      {record.bodyweight_kg
                        ? `${Math.round(Number(record.bodyweight_kg))}kg`
                        : "not weighed"}
                    </td>
                    <td className={`${tableCellClass} tabular-nums`}>
                      {record.ratio ? `${record.ratio}×` : "—"}
                    </td>
                    <td className={`${tableCellClass} text-[var(--color-text-muted)]`}>
                      {new Date(record.achieved_on).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Before the public board on purpose: a member who has opted out
          should meet the version that is for them first. */}
      <div className="mb-6">
        <PrivateStanding />
      </div>

      <Leaderboard optedIn={data.leaderboard_opt_in} />
    </div>
  );
}
