import { api } from "../lib/api";

/** 1–5. The rung, not the achievement: the badge's own name says what it was for. */
export type Tier = 1 | 2 | 3 | 4 | 5;

export const TIER_NAMES: Record<Tier, string> = {
  1: "Bronze",
  2: "Silver",
  3: "Gold",
  4: "Platinum",
  5: "Elite",
};

/** Used for the placeholder until the gym uploads its own artwork. */
export const TIER_COLOURS: Record<Tier, string> = {
  1: "#b06d3a",
  2: "#9aa4b2",
  3: "#ffb020",
  4: "#4f8dfd",
  5: "#a855f7",
};

export type Criterion =
  | "visits"
  | "streak"
  | "workouts"
  | "sets"
  | "records"
  | "months"
  | "classes"
  | "month_streak"
  /** The only criterion measured in kilograms, and the only one that needs an
      exercise — "100kg" means nothing without saying 100kg of what. */
  | "lift";

export interface Badge {
  id: number;
  code: string;
  name: string;
  description: string;
  tier: Tier;
  tier_name: string;
  /** Null until artwork is uploaded — the portal draws a placeholder. */
  image: string | null;
  criterion: Criterion;
  criterion_name: string;
  /** Set only on a lift badge. */
  exercise: number | null;
  exercise_name: string | null;
  /** A count, or kilograms for a lift badge. */
  threshold: number;
  is_active: boolean;
  awarded_count: number;
}

export interface BadgeProgress {
  badge: Badge;
  earned: boolean;
  awarded_on: string | null;
  /** What they had when it was awarded, or where they are now if locked. */
  value: number;
  threshold: number;
  percent: number;
}

export interface Achievements {
  current_streak: number;
  longest_streak: number;
  total_visits: number;
  earned_count: number;
  badge_count: number;
  /** Codes unlocked by this very request, so the screen can celebrate them. */
  newly_awarded: string[];
  badges: BadgeProgress[];
  leaderboard_opt_in: boolean;
}

export interface PersonalRecord {
  id: number;
  exercise: number;
  exercise_name: string;
  muscle_group: string;
  weight_kg: string;
  reps: number;
  /** What the member weighed on the day — not what they weigh now. */
  bodyweight_kg: string | null;
  ratio: string | null;
  achieved_on: string;
}

export interface LeaderboardRow {
  rank: number;
  member_id: number;
  username: string;
  full_name: string;
  exercise_id: number;
  exercise: string;
  weight_kg: string;
  reps: number;
  bodyweight_kg: string;
  ratio: string;
  achieved_on: string;
}

export async function fetchAchievements() {
  const res = await api.get<Achievements>("/gamification/achievements/");
  return res.data;
}

export async function fetchMyRecords() {
  const res = await api.get<PersonalRecord[]>("/gamification/records/");
  return res.data;
}

export async function fetchLeaderboard(exercise?: number) {
  const res = await api.get<{ month_start: string; results: LeaderboardRow[] }>(
    "/gamification/leaderboard/",
    { params: exercise ? { exercise } : undefined }
  );
  return res.data;
}

export async function setLeaderboardOptIn(optIn: boolean) {
  const res = await api.patch<{ leaderboard_opt_in: boolean }>("/gamification/me/", {
    leaderboard_opt_in: optIn,
  });
  return res.data;
}

/** Unpaginated, like the exercise and food catalogues. */
export async function fetchBadges() {
  const res = await api.get<Badge[] | { results: Badge[] }>("/gamification/badges/");
  return Array.isArray(res.data) ? res.data : res.data.results;
}

export async function saveBadge(payload: FormData) {
  const res = await api.post<Badge>("/gamification/badges/", payload);
  return res.data;
}

export async function updateBadge(id: number, payload: FormData) {
  const res = await api.patch<Badge>(`/gamification/badges/${id}/`, payload);
  return res.data;
}

export async function deleteBadge(id: number) {
  await api.delete(`/gamification/badges/${id}/`);
}


/** A personal record the member has not been shown yet. What it beat is
    derived on read from the record before it — nothing extra is stored. */
export interface PRCelebration {
  id: number;
  exercise: string;
  exercise_id: number;
  weight_kg: string;
  reps: number;
  achieved_on: string;
  previous_kg: string | null;
  gain_kg: string | null;
  /** Their first ever record on this lift — a different moment from beating one. */
  is_first: boolean;
  ratio: string | null;
}

/** Where the member sits, told only to them. Names nobody else. */
export interface Standing {
  month_start: string;
  exercise_id: number;
  ratio: string | null;
  pool: number;
  rank: number | null;
  /** "Top 10%" — rank as a share of the pool. */
  top_percent: number | null;
  /** "Better than 90%" — the share strictly below them. Both are given because
      the word "percentile" gets read both ways round. */
  better_than: number | null;
  /** Why there is no placing, when there isn't one. */
  reason: string | null;
}

export async function fetchNewRecords() {
  const res = await api.get<PRCelebration[]>("/gamification/records/new/");
  return res.data;
}

export async function acknowledgeRecords(ids: number[]) {
  const res = await api.post<{ seen: number }>("/gamification/records/new/", { ids });
  return res.data;
}

export async function fetchStanding(exercise: number) {
  const res = await api.get<Standing>("/gamification/leaderboard/me/", {
    params: { exercise },
  });
  return res.data;
}
