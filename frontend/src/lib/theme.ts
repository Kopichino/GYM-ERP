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
