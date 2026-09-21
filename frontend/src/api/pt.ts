import { api } from "../lib/api";

export type SessionStatus = "booked" | "completed" | "cancelled" | "no_show";

export interface Availability {
  id: number;
  trainer: number;
  trainer_name: string;
  /** 0 = Monday, matching Python's date.weekday(). */
  weekday: number;
  weekday_name: string;
  start_time: string;
  end_time: string;
  is_active: boolean;
}

export interface Unavailable {
  id: number;
  trainer: number;
  date: string;
  reason: string;
}

/** Derived from the weekly pattern minus blocked days minus bookings — there
    is no slot table behind this. */
export interface Slot {
  start_time: string;
  end_time: string;
}

export interface PTSession {
  id: number;
  trainer: number;
  trainer_name: string;
  member: number;
  member_name: string;
  date: string;
  start_time: string;
  end_time: string;
  status: SessionStatus;
  status_name: string;
  price: string;
  is_paid: boolean;
  is_past: boolean;
  notes: string;
  created_at: string;
}

export async function fetchAvailability(trainer?: number) {
  const res = await api.get<{ results: Availability[] }>("/pt/availability/", {
    params: trainer ? { trainer } : undefined,
  });
  return res.data.results;
}

export async function addAvailability(payload: {
  weekday: number;
  start_time: string;
  end_time: string;
}) {
  const res = await api.post<Availability>("/pt/availability/", payload);
  return res.data;
}

export async function deleteAvailability(id: number) {
  await api.delete(`/pt/availability/${id}/`);
}

export async function fetchUnavailable() {
  const res = await api.get<{ results: Unavailable[] }>("/pt/unavailable/");
  return res.data.results;
}

export async function addUnavailable(payload: { date: string; reason?: string }) {
  const res = await api.post<Unavailable>("/pt/unavailable/", payload);
  return res.data;
}

export async function deleteUnavailable(id: number) {
  await api.delete(`/pt/unavailable/${id}/`);
}

export async function fetchSlots(trainer: number, date: string) {
  const res = await api.get<{ trainer_name: string; date: string; results: Slot[] }>(
    "/pt/slots/",
    { params: { trainer, date } }
  );
  return res.data;
}

export async function fetchPTSessions(params?: { upcoming?: boolean; from?: string; to?: string }) {
  const res = await api.get<{ results: PTSession[] }>("/pt/sessions/", {
    params: params?.upcoming ? { upcoming: 1 } : params,
  });
  return res.data.results;
}

export async function bookPTSession(payload: {
  trainer: number;
  member: number;
  date: string;
  start_time: string;
  end_time: string;
}) {
  const res = await api.post<PTSession>("/pt/sessions/", payload);
  return res.data;
}

export async function cancelPTSession(id: number) {
  const res = await api.post<PTSession>(`/pt/sessions/${id}/cancel/`);
  return res.data;
}

export async function completePTSession(
  id: number,
  payload?: { no_show?: boolean; is_paid?: boolean }
) {
  const res = await api.post<PTSession>(`/pt/sessions/${id}/complete/`, payload ?? {});
  return res.data;
}

/** A trainer a member can book, as the booking form lists them. */
export interface BookableTrainer {
  id: number;
  name: string;
}

/**
 * The trainers at this gym. Replaces reading instructor profiles, which were
 * removed: a session is booked against the trainer's own account, so the list
 * comes straight from who holds a trainer role here.
 */
export async function fetchBookableTrainers() {
  const res = await api.get<{ results: BookableTrainer[] }>("/pt/trainers/");
  return res.data.results;
}
