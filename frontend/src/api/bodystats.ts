import { api } from "../lib/api";

export type GoalType = "weight" | "body_fat" | "attendance" | "custom";
export type GoalStatus = "active" | "achieved" | "archived";
export type BmiCategory = "underweight" | "normal" | "overweight" | "obese";

export interface BodyMeasurement {
  id: number;
  user: number;
  recorded_on: string;
  weight_kg: string;
  body_fat_pct: string | null;
  bmi: string | null;
  notes: string;
  recorded_by: number | null;
  recorded_by_name: string | null;
  created_at: string;
}

export interface BodyStatsSummary {
  height_cm: number | null;
  weight_kg: string | null;
  body_fat_pct: string | null;
  recorded_on: string | null;
  bmi: string | null;
  bmi_category: BmiCategory | null;
  change_since_previous: string | null;
  change_since_start: string | null;
  measurement_count: number;
}

export interface MemberGoal {
  id: number;
  user: number;
  goal_type: GoalType;
  label: string;
  title: string;
  start_value: string | null;
  target_value: string;
  current_value: string | null;
  live_value: string | null;
  progress_pct: string | null;
  target_date: string | null;
  status: GoalStatus;
  created_at: string;
}

/** `memberId` is only accepted for a trainer's assigned member or an admin. */
const scope = (memberId?: number) => (memberId ? { params: { member: memberId } } : undefined);

export async function fetchBodyStatsSummary(memberId?: number) {
  const res = await api.get<BodyStatsSummary>("/bodystats/summary/", scope(memberId));
  return res.data;
}

export async function fetchMeasurements(memberId?: number) {
  const res = await api.get<{ results: BodyMeasurement[] }>("/bodystats/measurements/", scope(memberId));
  return res.data.results;
}

export async function recordMeasurement(payload: {
  weight_kg: string;
  body_fat_pct?: string | null;
  recorded_on?: string;
  notes?: string;
  user?: number;
}) {
  const res = await api.post<BodyMeasurement>("/bodystats/measurements/", payload);
  return res.data;
}

export async function deleteMeasurement(id: number) {
  await api.delete(`/bodystats/measurements/${id}/`);
}

export async function fetchGoals(memberId?: number) {
  const res = await api.get<{ results: MemberGoal[] }>("/bodystats/goals/", scope(memberId));
  return res.data.results;
}

export async function createGoal(payload: {
  goal_type: GoalType;
  title?: string;
  start_value?: string | null;
  target_value: string;
  target_date?: string | null;
  user?: number;
}) {
  const res = await api.post<MemberGoal>("/bodystats/goals/", payload);
  return res.data;
}

export async function updateGoal(id: number, payload: Partial<MemberGoal>) {
  const res = await api.patch<MemberGoal>(`/bodystats/goals/${id}/`, payload);
  return res.data;
}

export async function deleteGoal(id: number) {
  await api.delete(`/bodystats/goals/${id}/`);
}

export async function updateMyProfile(profile: { height_cm?: number | null; phone?: string }) {
  const res = await api.patch("/auth/me/", { profile });
  return res.data;
}
