import { AnimatePresence, motion } from "framer-motion";
import { useMemo, useState } from "react";
import type { Exercise } from "../api/workouts";
import { getYouTubeThumbnail } from "../lib/youtube";
import { FALLBACK_MUSCLE_COLOR as FALLBACK_COLOR, MUSCLE_COLORS } from "../lib/theme";
import MuscleIcon from "./MuscleIcon";

type RegionMap = Map<string, Exercise[]>;
type MuscleMap = Map<string, RegionMap>;

function titleCase(text: string): string {
  return text
    .trim()
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function groupExercises(exercises: Exercise[]): MuscleMap {
  const muscles: MuscleMap = new Map();
  for (const exercise of exercises) {
    const muscle = exercise.muscle_group ? titleCase(exercise.muscle_group) : "Other";
    const region = exercise.region ? exercise.region.trim() : "General";
    if (!muscles.has(muscle)) muscles.set(muscle, new Map());
    const regions = muscles.get(muscle)!;
    if (!regions.has(region)) regions.set(region, []);
    regions.get(region)!.push(exercise);
  }
  return muscles;
}

function PlayIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className}>
      <path fill="currentColor" d="M8 5.5v13l11-6.5-11-6.5Z" />
    </svg>
  );
}

function ExerciseCard({
  exercise,
  color,
  index,
  muscle,
}: {
  exercise: Exercise;
  color: string;
  index: number;
  muscle: string;
}) {
  const video = exercise.videos[0];
  const thumb = video ? getYouTubeThumbnail(video.url) : null;

  const card = (
    <>
      {thumb ? (
        <img
          src={thumb}
          alt=""
          className="h-full w-full object-cover opacity-75 transition-opacity duration-300 group-hover:opacity-100"
        />
      ) : (
        <div
          className="flex h-full w-full items-center justify-center bg-[var(--color-surface-2)]"
          style={{ color }}
        >
          <MuscleIcon muscle={muscle} className="h-8 w-8 opacity-40" />
        </div>
      )}
      {video && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/25 opacity-0 transition-opacity duration-200 group-hover:opacity-100">
          <span
            className="flex h-10 w-10 items-center justify-center rounded-full"
            style={{ backgroundColor: color }}
          >
            <PlayIcon className="h-5 w-5 translate-x-[1px] text-white" />
          </span>
        </div>
      )}
      <p className="absolute inset-x-0 bottom-0 truncate bg-gradient-to-t from-black/85 to-transparent px-2.5 pb-1.5 pt-5 text-left text-[11.5px] font-semibold text-white">
        {exercise.name}
      </p>
    </>
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: Math.min(index * 0.03, 0.3) }}
    >
      {video ? (
        <motion.a
          href={video.url}
          target="_blank"
          rel="noopener noreferrer"
          initial={{ borderColor: "var(--color-border)" }}
          whileHover={{ borderColor: color, y: -2 }}
          transition={{ duration: 0.2 }}
          className="group relative block aspect-[4/3] w-full overflow-hidden rounded-lg border bg-[var(--color-surface-2)]"
        >
          {card}
        </motion.a>
      ) : (
        <div className="relative block aspect-[4/3] w-full overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)]">
          {card}
        </div>
      )}
    </motion.div>
  );
}

export default function MuscleLibrary({ exercises }: { exercises: Exercise[] }) {
  const grouped = useMemo(() => groupExercises(exercises), [exercises]);
  const muscles = useMemo(() => Array.from(grouped.keys()), [grouped]);
  const [active, setActive] = useState<string | null>(null);

  const regions = active ? grouped.get(active) : null;
  const activeColor = active ? MUSCLE_COLORS[active] ?? FALLBACK_COLOR : FALLBACK_COLOR;

  return (
    <div>
      <motion.div
        className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4"
        initial="hidden"
        animate="visible"
        variants={{ visible: { transition: { staggerChildren: 0.05 } } }}
      >
        {muscles.map((muscle) => {
          const color = MUSCLE_COLORS[muscle] ?? FALLBACK_COLOR;
          const count = Array.from(grouped.get(muscle)!.values()).reduce((n, list) => n + list.length, 0);
          const isActive = active === muscle;
          return (
            <motion.button
              key={muscle}
              variants={{ hidden: { opacity: 0, y: 14 }, visible: { opacity: 1, y: 0 } }}
              whileHover={{ y: -4, scale: 1.02 }}
              whileTap={{ scale: 0.97 }}
              onClick={() => setActive(isActive ? null : muscle)}
              className="relative overflow-hidden rounded-xl border p-4 text-left transition-colors"
              style={{
                borderColor: isActive ? color : "var(--color-border)",
                background: isActive
                  ? `linear-gradient(135deg, ${color}26, var(--color-surface))`
                  : "var(--color-surface)",
                boxShadow: isActive ? `0 0 0 1px ${color}, 0 8px 24px -8px ${color}80` : "none",
              }}
            >
              <div
                className="pointer-events-none absolute -right-4 -top-4 h-20 w-20 rounded-full opacity-20 blur-xl"
                style={{ background: color }}
              />
              <MuscleIcon muscle={muscle} className="relative mb-3 h-8 w-8" style={{ color }} />
              <h3 className="relative font-display text-lg uppercase tracking-wide text-[var(--color-text)]">
                {muscle}
              </h3>
              <p className="relative text-[11px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                {count} exercises
              </p>
            </motion.button>
          );
        })}
      </motion.div>

      <AnimatePresence mode="wait">
        {active && regions && (
          <motion.div
            key={active}
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.35, ease: "easeInOut" }}
            className="overflow-hidden"
          >
            <div className="mt-6 rounded-xl border p-4 sm:p-6" style={{ borderColor: `${activeColor}40` }}>
              <div className="mb-4 flex items-center justify-between">
                <h2 className="font-display text-2xl uppercase tracking-wide" style={{ color: activeColor }}>
                  {active}
                </h2>
                <button
                  onClick={() => setActive(null)}
                  className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
                >
                  Close
                </button>
              </div>
              <div className="flex flex-col gap-6">
                {Array.from(regions.entries()).map(([region, list]) => (
                  <div key={region}>
                    <h3 className="mb-2.5 flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-[var(--color-text-muted)]">
                      <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: activeColor }} />
                      {region}
                    </h3>
                    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                      {list.map((exercise, i) => (
                        <ExerciseCard
                          key={exercise.id}
                          exercise={exercise}
                          color={activeColor}
                          index={i}
                          muscle={active}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
