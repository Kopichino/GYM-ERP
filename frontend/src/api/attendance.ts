import { api } from "../lib/api";

export interface CheckInOut {
  id: number;
  user: number;
  check_in_time: string;
  check_out_time: string | null;
  method: "tap" | "qr" | "biometric" | "manual";
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

// -------------------------------------------------------------- QR check-in

export interface QrToken {
  token: string;
  expires_at: string;
  rotate_seconds: number;
}

/** The code the front-desk screen should show right now. Admin only. */
export async function fetchQrToken() {
  const res = await api.get<QrToken>("/attendance/qr_token/");
  return res.data;
}

export interface QrScanResult {
  action: "in" | "out";
  record: CheckInOut;
}

/** Posted by a member's phone after scanning the kiosk. One scan in, next out. */
export async function scanQr(token: string) {
  const res = await api.post<QrScanResult>("/attendance/qr-scan/", { token });
  return res.data;
}
