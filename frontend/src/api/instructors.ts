import { api } from "../lib/api";

export interface Instructor {
  id: number;
  name: string;
  bio: string;
  specialty: string;
  photo: string | null;
  active: boolean;
}

export async function fetchInstructors() {
  const res = await api.get<{ results: Instructor[] }>("/instructors/");
  return res.data.results;
}

export async function createInstructor(payload: FormData) {
  const res = await api.post<Instructor>("/instructors/", payload, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data;
}

export async function deleteInstructor(id: number) {
  await api.delete(`/instructors/${id}/`);
}
