import { api } from "../lib/api";

export interface DayPass {
  id: number;
  name: string;
  phone: string;
  email: string;
  /** A pass is good for one named day. */
  valid_on: string;
  amount: string;
  method: string;
  notes: string;
  issued_by: number | null;
  issued_by_name: string | null;
  is_valid_today: boolean;
  /** Both derived from the visit rows — no flag on the pass to go stale. */
  visit_count: number;
  checked_in: boolean;
  created_at: string;
}

export async function fetchDayPasses(params?: { on?: string; from?: string; to?: string }) {
  const res = await api.get<{ results: DayPass[] }>("/billing/day-passes/", { params });
  return res.data.results;
}

export async function createDayPass(payload: {
  name: string;
  phone?: string;
  email?: string;
  valid_on?: string;
  amount?: string;
  method?: string;
  notes?: string;
}) {
  const res = await api.post<DayPass>("/billing/day-passes/", payload);
  return res.data;
}

/** One tap in, the next tap out — the same shape as a member check-in. */
export async function checkInDayPass(id: number) {
  const res = await api.post<{ action: "in" | "out" }>(
    `/billing/day-passes/${id}/check_in/`
  );
  return res.data;
}

export async function deleteDayPass(id: number) {
  await api.delete(`/billing/day-passes/${id}/`);
}
