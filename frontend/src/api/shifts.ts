import { api } from "../lib/api";

/** What someone is on the floor to do — separate from their account role, so a
    trainer can cover the desk without becoming an admin. */
export type Position =
  | "floor"
  | "front_desk"
  | "pt"
  | "classes"
  | "cleaning"
  | "management";

export const POSITIONS: { value: Position; label: string }[] = [
  { value: "floor", label: "Gym floor" },
  { value: "front_desk", label: "Front desk" },
  { value: "pt", label: "Personal training" },
  { value: "classes", label: "Classes" },
  { value: "cleaning", label: "Cleaning" },
  { value: "management", label: "Management" },
];

export interface Shift {
  id: number;
  staff: number;
  staff_name: string;
  staff_role: string;
  date: string;
  start_time: string;
  end_time: string;
  /** Derived from the two times, never stored. */
  hours: number;
  position: Position;
  position_name: string;
  notes: string;
  created_by: number | null;
  created_at: string;
}

export async function fetchShifts(params?: {
  from?: string;
  to?: string;
  staff?: number;
  position?: Position;
}) {
  const res = await api.get<{ results: Shift[] }>("/shifts/", { params });
  return res.data.results;
}

/** The caller's own upcoming shifts. */
export async function fetchMyShifts() {
  const res = await api.get<Shift[]>("/shifts/mine/");
  return res.data;
}

/** Who is rostered at this moment — read off the rota, not a flag. */
export async function fetchOnFloor() {
  const res = await api.get<{ at: string; count: number; results: Shift[] }>(
    "/shifts/on_floor/"
  );
  return res.data;
}

export async function createShift(payload: {
  staff: number;
  date: string;
  start_time: string;
  end_time: string;
  position: Position;
  notes?: string;
}) {
  const res = await api.post<Shift>("/shifts/", payload);
  return res.data;
}

export async function deleteShift(id: number) {
  await api.delete(`/shifts/${id}/`);
}
