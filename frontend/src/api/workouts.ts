import { api } from "../lib/api";

export interface ExerciseVideo {
  id: number;
  title: string;
  url: string;
  order: number;
}

export interface Exercise {
  id: number;
  name: string;
  category: string;
  muscle_group: string;
  region: string;
  videos: ExerciseVideo[];
}

export interface WorkoutLog {
  id: number;
  session: number;
  exercise: number;
  exercise_name: string;
  set_number: number;
  reps: number;
  weight: string;
  weight_unit: "kg" | "lb";
}

export interface WorkoutSession {
  id: number;
  user: number;
  user_name: string;
  date: string;
  notes: string;
  logs: WorkoutLog[];
}

export interface ProgressPoint {
  session__date: string;
  max_weight: string;
  total_reps: number;
  weight_unit: "kg" | "lb";
}

export async function fetchExercises() {
  const res = await api.get<{ results: Exercise[] } | Exercise[]>("/workouts/exercises/");
  return Array.isArray(res.data) ? res.data : res.data.results;
}

export async function fetchSessions(memberId?: number) {
  const res = await api.get<{ results: WorkoutSession[] }>("/workouts/sessions/", {
    params: memberId ? { member: memberId } : undefined,
  });
  return res.data.results;
}

export async function createSession(notes: string, memberId?: number) {
  const res = await api.post<WorkoutSession>("/workouts/sessions/", {
    notes,
    ...(memberId ? { user: memberId } : {}),
  });
  return res.data;
}

export async function addLog(payload: {
  session: number;
  exercise: number;
  set_number: number;
  reps: number;
  weight: number;
  weight_unit: "kg" | "lb";
}) {
  const res = await api.post<WorkoutLog>("/workouts/logs/", payload);
  return res.data;
}

export async function fetchProgress(exerciseId: number, memberId?: number) {
  const res = await api.get<ProgressPoint[]>("/workouts/sessions/progress/", {
    params: { exercise: exerciseId, ...(memberId ? { member: memberId } : {}) },
  });
  return res.data;
}

// ---------------------------------------------------------------- splits

export const WEEKDAYS = [
  "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
] as const;

export interface SplitExercise {
  id: number;
  day: number;
  exercise: number;
  exercise_name: string;
  muscle_group: string;
  region: string;
  videos: ExerciseVideo[];
  order: number;
  target_sets: number | null;
  target_reps: string;
}

export interface SplitDay {
  id: number;
  split: number;
  /** 0 = Monday, matching Python's date.weekday(). */
  weekday: number;
  weekday_name: string;
  label: string;
  display_label: string;
  target_muscles: string[];
  notes: string;
  exercises: SplitExercise[];
}

export interface WorkoutSplit {
  id: number;
  user: number;
  name: string;
  is_active: boolean;
  days_per_week: number;
  days: SplitDay[];
  created_at: string;
}

export interface TodaySplit {
  is_training_day: boolean;
  weekday_name: string;
  has_split: boolean;
  day: SplitDay | null;
}

export async function fetchSplits() {
  const res = await api.get<{ results: WorkoutSplit[] }>("/workouts/splits/");
  return res.data.results;
}

export async function fetchTodaySplit(memberId?: number) {
  const res = await api.get<TodaySplit>("/workouts/splits/today/", {
    params: memberId ? { member: memberId } : undefined,
  });
  return res.data;
}

/** A new split always becomes the current one; the server retires the old. */
export async function createSplit(name: string) {
  const res = await api.post<WorkoutSplit>("/workouts/splits/", { name });
  return res.data;
}

export async function deleteSplit(id: number) {
  await api.delete(`/workouts/splits/${id}/`);
}

export async function addSplitDay(payload: {
  split: number;
  weekday: number;
  label?: string;
  target_muscles: string[];
}) {
  const res = await api.post<SplitDay>("/workouts/split-days/", payload);
  return res.data;
}

export async function updateSplitDay(id: number, payload: Partial<SplitDay>) {
  const res = await api.patch<SplitDay>(`/workouts/split-days/${id}/`, payload);
  return res.data;
}

export async function deleteSplitDay(id: number) {
  await api.delete(`/workouts/split-days/${id}/`);
}

export async function addSplitExercise(payload: {
  day: number;
  exercise: number;
  target_sets?: number | null;
  target_reps?: string;
}) {
  const res = await api.post<SplitExercise>("/workouts/split-exercises/", payload);
  return res.data;
}

export async function deleteSplitExercise(id: number) {
  await api.delete(`/workouts/split-exercises/${id}/`);
}
