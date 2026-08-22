import { api } from "../lib/api";

export interface ClassSession {
  id: number;
  title: string;
  instructor: number | null;
  instructor_name: string | null;
  date: string;
  start_time: string;
  end_time: string;
  capacity: number | null;
  description: string;
}

export async function fetchClassSessions() {
  const res = await api.get<{ results: ClassSession[] }>("/schedule/");
  return res.data.results;
}

export async function createClassSession(payload: Omit<ClassSession, "id" | "instructor_name">) {
  const res = await api.post<ClassSession>("/schedule/", payload);
  return res.data;
}

export async function deleteClassSession(id: number) {
  await api.delete(`/schedule/${id}/`);
}
