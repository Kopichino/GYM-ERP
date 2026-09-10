/** Shared per-muscle accent colors -- used by the exercise library and
 * anywhere else (e.g. billing status badges) that wants a consistent,
 * centralized palette instead of redefining its own. */
export const MUSCLE_COLORS: Record<string, string> = {
  Chest: "#ff3d5a",
  Back: "#4f8dfd",
  Shoulders: "#ffb020",
  Biceps: "#22c55e",
  Triceps: "#a855f7",
  Legs: "#06b6d4",
  Abs: "#f97316",
};
export const FALLBACK_MUSCLE_COLOR = "#ff3d5a";

/**
 * Rail colours for the line along the top of each Card.
 *
 * Drawn from the same hues the muscle-group palette already uses, so the app
 * keeps one colour vocabulary rather than gaining a second one. Cards sitting
 * together in a view step through this list so a panel is distinguishable at a
 * glance; a card whose colour already *means* something (a role, a status, a
 * muscle) passes that colour explicitly instead.
 */
export const RAIL_COLORS = [
  "#ff3d5a", // crimson — the brand accent
  "#4f8dfd", // blue
  "#22c55e", // green
  "#ffb020", // amber
  "#a855f7", // purple
  "#06b6d4", // cyan
  "#f97316", // orange
];

/** Rail colour for the nth card in a view. Wraps, so any length is safe. */
export function railColor(index: number) {
  return RAIL_COLORS[index % RAIL_COLORS.length];
}

/** Status -> accent color, used for billing/membership badges. */
export const STATUS_COLORS: Record<string, string> = {
  active: "#22c55e",
  completed: "#22c55e",
  paused: "#ffb020",
  pending: "#ffb020",
  expired: "#ff3d5a",
  failed: "#ff3d5a",
  refunded: "#9494a8",
};
export const FALLBACK_STATUS_COLOR = "#9494a8";

/**
 * What a colour *means*, as opposed to which position a card happens to sit in.
 *
 * `railColor` above is decoration: it steps through hues so a row of unrelated
 * panels is distinguishable. That is fine for a panel with no state, and wrong
 * for anything carrying a status -- it had monthly revenue wearing the danger
 * colour and 0% churn wearing a caution colour, purely because of where they
 * fell in the list.
 *
 * Four meanings, and only four. The temptation is to add "info-but-important"
 * or "good-but-not-great"; every one of those makes the vocabulary less
 * readable, because a reader has to learn the difference before the colour
 * tells them anything.
 */
export type Status = "positive" | "caution" | "negative" | "neutral";

/**
 * Tokens rather than constants, so a status follows the theme.
 *
 * These were literal hexes, which was fine while there was one theme. They are
 * mostly used on small text, and #22c55e on white is about 2.2:1 -- so a light
 * mode built on the same constants would have shipped unreadable "Active"
 * labels. The light values live beside the dark ones in `index.css`.
 */
export const STATUS_COLOR_BY_MEANING: Record<Status, string> = {
  /** Healthy, done, paid, active. Never merely "finished". */
  positive: "var(--status-positive)",
  /** Needs a human to look at it. Not yet a problem. */
  caution: "var(--status-caution)",
  /** A problem, or an action that destroys something. */
  negative: "var(--status-negative)",
  /** A number with no opinion attached -- revenue, counts, totals. */
  neutral: "var(--status-neutral)",
};

export function statusColor(status: Status) {
  return STATUS_COLOR_BY_MEANING[status];
}

/**
 * A washed-out version of a colour, for the fill behind a pill.
 *
 * Appending "22" to a hex was how this was done, and it silently produces
 * `var(--status-positive)22` -- an invalid colour that renders as nothing --
 * now that these are tokens. `color-mix` works for both.
 */
export function tint(color: string, percent = 14) {
  return `color-mix(in srgb, ${color} ${percent}%, transparent)`;
}

/**
 * Turns a measured value into a meaning, given where the thresholds sit.
 *
 * For metrics where the number itself decides whether it is good news: churn
 * at 0% is healthy and should read green, the same metric at 20% should not.
 * A fixed colour cannot say that, which is why the dashboard used to show
 * "0% churn" in amber.
 *
 * `lowerIsBetter` covers the two directions -- churn wants to be small, class
 * fill wants to be large -- so both can share one function rather than one
 * growing an inverted copy.
 */
export function thresholdStatus(
  value: number,
  { good, bad, lowerIsBetter = true }: { good: number; bad: number; lowerIsBetter?: boolean },
): Status {
  if (Number.isNaN(value)) return "neutral";
  const healthy = lowerIsBetter ? value <= good : value >= good;
  const failing = lowerIsBetter ? value >= bad : value <= bad;
  if (healthy) return "positive";
  if (failing) return "negative";
  return "caution";
}
