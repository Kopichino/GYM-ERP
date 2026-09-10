import { api } from "../lib/api";

export interface Instructor {
  id: number;
  user: number | null;
  username: string | null;
  name: string;
  bio: string;
  specialty: string;
  photo: string | null;
  active: boolean;
}

/** The signed-in trainer's own profile -- the one they may edit themselves. */
export async function fetchMyInstructorProfile() {
  const res = await api.get<Instructor>("/instructors/me/");
  return res.data;
}

export async function updateMyInstructorProfile(payload: FormData) {
  const res = await api.patch<Instructor>("/instructors/me/", payload, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data;
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
