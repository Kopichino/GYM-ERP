import { api } from "../lib/api";

export interface CheckInOut {
  id: number;
  user: number;
  check_in_time: string;
  check_out_time: string | null;
}

export async function fetchCurrentCheckIn() {
  const res = await api.get<CheckInOut>("/attendance/current/");
  return res.status === 204 ? null : res.data;
}

export async function fetchCheckInHistory() {
  const res = await api.get<{ results: CheckInOut[] }>("/attendance/");
  return res.data.results;
}

export async function checkIn() {
  const res = await api.post<CheckInOut>("/attendance/check_in/");
  return res.data;
}

export async function checkOut() {
  const res = await api.post<CheckInOut>("/attendance/check_out/");
  return res.data;
}

export interface CalendarData {
  dates: string[];
  total_visits: number;
  current_streak: number;
  longest_streak: number;
}

export async function fetchCalendar() {
  const res = await api.get<CalendarData>("/attendance/calendar/");
  return res.data;
}
