import { api } from "../lib/api";

export interface Exercise {
  id: number;
  name: string;
  category: string;
  muscle_group: string;
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
  date: string;
  notes: string;
  logs: WorkoutLog[];
}

export interface ProgressPoint {
  session__date: string;
  max_weight: string;
  total_reps: number;
}

export async function fetchExercises() {
  const res = await api.get<{ results: Exercise[] } | Exercise[]>("/workouts/exercises/");
  return Array.isArray(res.data) ? res.data : res.data.results;
}

export async function fetchSessions() {
  const res = await api.get<{ results: WorkoutSession[] }>("/workouts/sessions/");
  return res.data.results;
}

export async function createSession(notes: string) {
  const res = await api.post<WorkoutSession>("/workouts/sessions/", { notes });
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

export async function fetchProgress(exerciseId: number) {
  const res = await api.get<ProgressPoint[]>("/workouts/sessions/progress/", {
    params: { exercise: exerciseId },
  });
  return res.data;
}
