import { api } from "../lib/api";

export type EventOutcome =
  | "pending"
  | "checked_in"
  | "checked_out"
  | "unmatched"
  | "duplicate"
  /** Someone real, refused entry by a gate. */
  | "denied"
  | "failed";

/** What the hardware does — only a gate may refuse someone. */
export type DeviceKind = "terminal" | "turnstile" | "door";

export const DEVICE_KINDS: { value: DeviceKind; label: string }[] = [
  { value: "terminal", label: "Attendance terminal" },
  { value: "turnstile", label: "Turnstile" },
  { value: "door", label: "Door lock" },
];

export interface Device {
  id: number;
  name: string;
  serial: string;
  location: string;
  kind: DeviceKind;
  kind_name: string;
  /** Days past expiry a lapsed member may still come through a gate. */
  grace_days: number;
  is_active: boolean;
  last_seen_at: string | null;
  event_count: number;
  created_at: string;
}

export interface DeviceEvent {
  id: number;
  device: number;
  device_name: string;
  biometric_id: string;
  event_time: string;
  outcome: EventOutcome;
  detail: string;
  member: number | null;
  member_name: string | null;
  check_in: number | null;
  received_at: string;
}

export async function fetchDevices() {
  const res = await api.get<{ results: Device[] }>("/devices/");
  return res.data.results;
}

/** The plaintext key comes back exactly once, on registration. */
export async function registerDevice(payload: {
  name: string;
  serial: string;
  location?: string;
  kind?: DeviceKind;
  grace_days?: number;
}) {
  const res = await api.post<Device & { api_key: string }>("/devices/", payload);
  return res.data;
}

export async function updateDevice(id: number, payload: Partial<Device>) {
  const res = await api.patch<Device>(`/devices/${id}/`, payload);
  return res.data;
}

export async function rotateDeviceKey(id: number) {
  const res = await api.post<{ api_key: string }>(`/devices/${id}/rotate_key/`);
  return res.data;
}

export async function deleteDevice(id: number) {
  await api.delete(`/devices/${id}/`);
}

export async function fetchDeviceEvents(params?: { outcome?: EventOutcome; device?: number }) {
  const res = await api.get<{ results: DeviceEvent[] }>("/devices/events/", { params });
  return res.data.results;
}

export async function reprocessEvent(id: number) {
  const res = await api.post<DeviceEvent>(`/devices/events/${id}/reprocess/`);
  return res.data;
}
