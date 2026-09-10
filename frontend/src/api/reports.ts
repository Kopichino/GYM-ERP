import { api } from "../lib/api";

export interface DateWindow {
  start?: string;
  end?: string;
}

export interface RevenueReport {
  start: string;
  end: string;
  collected: string;
  discounts_given: string;
  gross: string;
  expenses: string;
  net: string;
  payment_count: number;
  by_month: { month: string; total: string; count: number }[];
  by_plan: { plan: string; total: string; count: number }[];
  by_method: { method: string; total: string }[];
}

export interface AttendanceReport {
  start: string;
  end: string;
  total_visits: number;
  unique_members: number;
  member_count: number;
  participation_pct: number;
  by_day: { date: string; count: number }[];
  by_method: { method: string; count: number }[];
  by_hour: { hour: number; count: number }[];
}

export interface ChurnReport {
  start: string;
  end: string;
  grace_days: number;
  /** Stated on screen, because "churn" has no single agreed meaning. */
  definition: string;
  churned_count: number;
  retained_count: number;
  churn_rate_pct: number;
  members: {
    member: string;
    name: string;
    expired_on: string;
    days_lapsed: number;
    last_plan: string;
  }[];
}

export interface PtPerformanceReport {
  start: string;
  end: string;
  trainers: {
    trainer: string;
    name: string;
    member_count: number;
    revenue: string;
    payment_count: number;
    commission: string;
    member_visits: number;
  }[];
}

export interface ReportSource {
  source: string;
  label: string;
  fields: string[];
}

export interface CustomResult {
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
}

export interface ReportDefinition {
  source: string;
  fields?: string[];
  group_by?: string;
  aggregates?: { fn: string; field?: string; alias?: string }[];
  filters?: { field: string; op: string; value: unknown }[];
  start?: string;
  end?: string;
}

export interface SavedReport {
  id: number;
  name: string;
  description: string;
  definition: ReportDefinition;
  owner_name: string | null;
  created_at: string;
}

const params = (w: DateWindow) => ({ params: { start: w.start, end: w.end } });

export async function fetchRevenue(w: DateWindow = {}) {
  return (await api.get<RevenueReport>("/reports/revenue/", params(w))).data;
}
export async function fetchAttendanceReport(w: DateWindow = {}) {
  return (await api.get<AttendanceReport>("/reports/attendance/", params(w))).data;
}
export async function fetchChurn(w: DateWindow = {}) {
  return (await api.get<ChurnReport>("/reports/churn/", params(w))).data;
}
export async function fetchPtPerformance(w: DateWindow = {}) {
  return (await api.get<PtPerformanceReport>("/reports/pt-performance/", params(w))).data;
}
export async function fetchReportSchema() {
  return (await api.get<ReportSource[]>("/reports/schema/")).data;
}
export async function runCustomReport(definition: ReportDefinition) {
  return (await api.post<CustomResult>("/reports/custom/", definition)).data;
}
export async function fetchSavedReports() {
  return (await api.get<{ results: SavedReport[] }>("/reports/saved/")).data.results;
}
export async function saveReport(payload: {
  name: string;
  description?: string;
  definition: ReportDefinition;
}) {
  return (await api.post<SavedReport>("/reports/saved/", payload)).data;
}
export async function deleteSavedReport(id: number) {
  await api.delete(`/reports/saved/${id}/`);
}

export async function exportReport(definition: ReportDefinition) {
  const res = await api.post("/reports/export/", definition, { responseType: "blob" });
  const url = window.URL.createObjectURL(new Blob([res.data]));
  const link = document.createElement("a");
  link.href = url;
  link.setAttribute("download", "ironcore_report.xlsx");
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

// -------------------------------------------------------------- owner KPIs

export interface RateBlock {
  rate: number;
}

export interface Kpis {
  from: string;
  to: string;
  active_members: number;
  paused_members: number;
  /** Every live membership's price normalised to 30 days. */
  mrr: string;
  arpm: string;
  collected: string;
  visits: number;
  churn: { lapsed: number; considered: number; rate: number };
  pt: { booked_hours: number; offered_hours: number; rate: number };
  classes: { sessions: number; seats: number; booked: number; rate: number };
  /** What each figure counts — shown on screen, not left to be assumed. */
  definitions: Record<string, string>;
}

export interface Occupancy {
  from: string;
  to: string;
  total_visits: number;
  peak: number;
  busiest: { weekday: number; hour: number; visits: number } | null;
  /** [weekday 0=Monday][hour 0-23] -> visits. */
  grid: number[][];
}

export async function fetchKpis(params?: { start?: string; end?: string }) {
  const res = await api.get<Kpis>("/reports/kpis/", { params });
  return res.data;
}

export async function fetchOccupancy(params?: { start?: string; end?: string }) {
  const res = await api.get<Occupancy>("/reports/occupancy/", { params });
  return res.data;
}
