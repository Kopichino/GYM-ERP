import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { acknowledgeRecords, fetchNewRecords } from "../api/gamification";
import { Button } from "./ui";

const GOLD = "#ffb020";

/**
 * The "new PR" moment.
 *
 * Renders nothing at all unless there is genuinely a record the member has not
 * been shown, which is almost always — so this costs one indexed lookup and no
 * layout on an ordinary page load.
 *
 * Deliberately a small panel rather than a full-screen takeover: it appears
 * mid-session, while somebody is between sets, and a modal they have to dismiss
 * to get back to logging would be a punishment for lifting well.
 */
export default function PRCelebration() {
  const queryClient = useQueryClient();

  const { data: records } = useQuery({
    queryKey: ["records", "new"],
    queryFn: fetchNewRecords,
  });

  const dismiss = useMutation({
    mutationFn: (ids: number[]) => acknowledgeRecords(ids),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["records", "new"] });
      // A PR can complete a lift badge, so the achievements screen is stale.
      queryClient.invalidateQueries({ queryKey: ["achievements"] });
    },
  });

  if (!records?.length) return null;

  const ids = records.map((row) => row.id);

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.25 }}
        className="rounded-xl border p-4"
        style={{
          borderColor: GOLD,
          background: `linear-gradient(140deg, color-mix(in srgb, ${GOLD} 14%, var(--color-surface)), var(--color-surface))`,
        }}
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="font-display text-2xl uppercase tracking-wide" style={{ color: GOLD }}>
              {records.length === 1 ? "New personal record" : `${records.length} new records`}
            </p>

            <ul className="mt-2 flex flex-col gap-1.5">
              {records.slice(0, 4).map((record) => (
                <li key={record.id} className="text-sm text-[var(--color-text)]">
                  <b>{record.exercise}</b>{" "}
                  <span className="tabular-nums">
                    {Number(record.weight_kg)}kg × {record.reps}
                  </span>
                  <span className="ml-2 text-[var(--color-text-muted)]">
                    {record.is_first
                      ? "— your first one on this lift"
                      : `— up ${Number(record.gain_kg)}kg on your old best of ${Number(
                          record.previous_kg
                        )}kg`}
                  </span>
                </li>
              ))}
              {records.length > 4 && (
                <li className="text-sm text-[var(--color-text-muted)]">
                  and {records.length - 4} more
                </li>
              )}
            </ul>
          </div>

          <Button
            variant="secondary"
            onClick={() => dismiss.mutate(ids)}
            disabled={dismiss.isPending}
            className="px-3 py-1 text-xs"
          >
            Nice
          </Button>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
