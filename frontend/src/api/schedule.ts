import { api } from "../lib/api";

export type BookingStatus = "booked" | "waitlisted" | "cancelled" | "attended";

export interface ClassSession {
  id: number;
  title: string;
  /** The trainer running the class -- their own account, not a separate profile. */
  trainer: number | null;
  trainer_name: string | null;
  date: string;
  start_time: string;
  end_time: string;
  capacity: number | null;
  description: string;
  booked_count: number;
  /** null when the class is uncapped. */
  spots_left: number | null;
  /** The signed-in member's own place, or null if they have none. */
  my_status: BookingStatus | null;
}

export interface ClassBooking {
  id: number;
  member: number;
  member_name: string;
  session: number;
  session_title: string;
  date: string;
  start_time: string;
  end_time: string;
  trainer_name: string | null;
  status: BookingStatus;
  position: number | null;
  booked_at: string;
}

export async function bookClass(sessionId: number) {
  const res = await api.post<ClassBooking>(`/schedule/${sessionId}/book/`);
  return res.data;
}

export async function cancelBooking(sessionId: number) {
  const res = await api.post<{
    booking: ClassBooking;
    promoted_from_waitlist: ClassBooking | null;
  }>(`/schedule/${sessionId}/cancel/`);
  return res.data;
}

export async function fetchMyBookings() {
  const res = await api.get<{ results: ClassBooking[] }>("/schedule/my-bookings/");
  return res.data.results;
}

export async function fetchRoster(sessionId: number) {
  const res = await api.get<ClassBooking[]>(`/schedule/${sessionId}/roster/`);
  return res.data;
}

export async function markAttendance(sessionId: number, memberIds: number[]) {
  const res = await api.post<{ marked_attended: number }>(
    `/schedule/${sessionId}/attendance/`,
    { member_ids: memberIds }
  );
  return res.data;
}

export async function fetchClassSessions(mineOnly = false) {
  const res = await api.get<{ results: ClassSession[] }>("/schedule/", {
    params: mineOnly ? { mine: 1 } : undefined,
  });
  return res.data.results;
}

/** The writable half of a class -- seat counts and my_status are computed. */
export type ClassSessionInput = Pick<
  ClassSession,
  "title" | "trainer" | "date" | "start_time" | "end_time" | "capacity" | "description"
>;

export async function createClassSession(payload: ClassSessionInput) {
  const res = await api.post<ClassSession>("/schedule/", payload);
  return res.data;
}

export async function deleteClassSession(id: number) {
  await api.delete(`/schedule/${id}/`);
}
