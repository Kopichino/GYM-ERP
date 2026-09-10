import { api } from "../lib/api";

export type EnquiryStatus = "open" | "contacted" | "trial" | "joined" | "lost";

export type EnquirySource =
  | "walk_in"
  | "phone"
  | "instagram"
  | "facebook"
  | "google"
  | "referral"
  | "other";

export const ENQUIRY_SOURCES: { value: EnquirySource; label: string }[] = [
  { value: "walk_in", label: "Walked in" },
  { value: "phone", label: "Phone call" },
  { value: "instagram", label: "Instagram" },
  { value: "facebook", label: "Facebook" },
  { value: "google", label: "Google / search" },
  { value: "referral", label: "Member referral" },
  { value: "other", label: "Other" },
];

export interface EnquiryNote {
  id: number;
  enquiry: number;
  body: string;
  author: number | null;
  author_name: string | null;
  created_at: string;
}

export interface Enquiry {
  id: number;
  name: string;
  phone: string;
  /** Date only — the desk picks a day to call, never a time. */
  follow_up_on: string;
  status: EnquiryStatus;
  source: EnquirySource;
  source_name: string;
  email: string;
  interested_in: number | null;
  interested_in_name: string | null;
  assigned_to: number | null;
  assigned_to_name: string | null;
  converted_user: number | null;
  converted_username: string | null;
  notes: string;
  last_contacted_on: string | null;
  is_due: boolean;
  is_converted: boolean;
  days_overdue: number;
  /** Newest first. Appended to, never overwritten. */
  trail: EnquiryNote[];
  created_by: number | null;
  created_by_name: string | null;
  created_at: string;
}

export interface PipelineStats {
  total: number;
  converted: number;
  conversion_rate: number;
  by_status: { status: EnquiryStatus; status_name: string; count: number }[];
  by_source: {
    source: EnquirySource;
    source_name: string;
    total: number;
    joined: number;
    conversion_rate: number;
  }[];
}

export interface DueEnquiries {
  date: string;
  count: number;
  overdue_count: number;
  results: Enquiry[];
}

export async function fetchEnquiries(filters?: {
  status?: EnquiryStatus;
  source?: EnquirySource;
}) {
  const res = await api.get<{ results: Enquiry[] }>("/crm/enquiries/", {
    params: {
      status: filters?.status || undefined,
      source: filters?.source || undefined,
    },
  });
  return res.data.results;
}

/** Today's callbacks plus anything already missed — drives the reminder. */
export async function fetchDueEnquiries() {
  const res = await api.get<DueEnquiries>("/crm/enquiries/due/");
  return res.data;
}

export async function createEnquiry(payload: {
  name: string;
  phone: string;
  follow_up_on: string;
  source?: EnquirySource;
  email?: string;
  interested_in?: number | null;
  notes?: string;
}) {
  const res = await api.post<Enquiry>("/crm/enquiries/", payload);
  return res.data;
}

export async function updateEnquiry(id: number, payload: Partial<Enquiry>) {
  const res = await api.patch<Enquiry>(`/crm/enquiries/${id}/`, payload);
  return res.data;
}

/** Log the call. Pass `follow_up_on` to reschedule instead of closing it. */
export async function markCalled(id: number, followUpOn?: string) {
  const res = await api.post<Enquiry>(
    `/crm/enquiries/${id}/mark_called/`,
    followUpOn ? { follow_up_on: followUpOn } : {}
  );
  return res.data;
}

export async function deleteEnquiry(id: number) {
  await api.delete(`/crm/enquiries/${id}/`);
}

/** Counts by stage and by source, read live from the leads themselves. */
export async function fetchPipeline() {
  const res = await api.get<PipelineStats>("/crm/enquiries/pipeline/");
  return res.data;
}

/** Appends to the lead's trail. Never overwrites the last entry. */
export async function addEnquiryNote(id: number, body: string) {
  const res = await api.post<EnquiryNote>(`/crm/enquiries/${id}/note/`, { body });
  return res.data;
}

export interface ConversionResult {
  user_id: number;
  username: string;
  enquiry: Enquiry;
}

/** Turns the lead into a member account and closes any referral behind it. */
export async function convertEnquiry(
  id: number,
  payload?: { username?: string; email?: string }
) {
  const res = await api.post<ConversionResult>(`/crm/enquiries/${id}/convert/`, payload ?? {});
  return res.data;
}

export async function fetchSuggestedUsername(id: number) {
  const res = await api.get<{ username: string }>(`/crm/enquiries/${id}/suggested_username/`);
  return res.data.username;
}

// ------------------------------------------------------------- retention

export type RiskBand = "quiet" | "cooling";

export interface AtRiskMember {
  id: number;
  username: string;
  full_name: string;
  phone: string;
  email: string;
  trainer: string | null;
  membership_status: string;
  last_visit: string | null;
  days_since_visit: number;
  /** True when they joined but have never checked in at all. */
  never_visited: boolean;
  band: RiskBand;
  expires_on: string | null;
  days_left: number | null;
}

export interface AtRiskReport {
  quiet_days: number;
  cooling_days: number;
  grace_days: number;
  quiet_count: number;
  cooling_count: number;
  /** Worst absence first — the order a call list is worked in. */
  results: AtRiskMember[];
}

export interface RetentionPolicy {
  id: number;
  quiet_days: number;
  cooling_days: number;
  grace_days: number;
  is_active: boolean;
  updated_at: string;
}

/** Derived on every read: a member who checks in drops off without any flag
    being cleared. Trainers get their own roster, admins get the gym. */
export async function fetchAtRisk() {
  const res = await api.get<AtRiskReport>("/crm/at-risk/");
  return res.data;
}

export async function fetchRetentionPolicies() {
  const res = await api.get<{ results: RetentionPolicy[] }>("/crm/retention/");
  return res.data.results;
}

export async function saveRetentionPolicy(payload: {
  quiet_days: number;
  cooling_days: number;
  grace_days: number;
}) {
  const res = await api.post<RetentionPolicy>("/crm/retention/", payload);
  return res.data;
}
