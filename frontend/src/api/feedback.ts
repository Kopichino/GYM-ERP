import { api } from "../lib/api";

export type Trigger = "post_checkin" | "post_pt" | "manual";

export interface Survey {
  id: number;
  title: string;
  question: string;
  trigger: Trigger;
  trigger_name: string;
  cooldown_days: number;
  is_active: boolean;
  response_count: number;
  created_at: string;
}

/** A prompt the member is owed. Derived from an unanswered visit or session —
    there is no pending-prompt table behind this. */
export interface PendingPrompt {
  survey: Survey;
  visit: number | null;
  pt_session: number | null;
}

export interface DetractorComment {
  id: number;
  score: number;
  comment: string;
  member: string;
  member_id: number;
  created_at: string;
}

export interface NpsBands {
  responses: number;
  promoters: number;
  passives: number;
  detractors: number;
  /** null when nobody has answered — 0 is a real score, "no answers" is not. */
  nps: number | null;
  average: number | null;
}

export interface NpsSummary extends NpsBands {
  definition: string;
  detractor_comments: DetractorComment[];
  trend: (NpsBands & { month: string })[];
}

export async function fetchSurveys() {
  const res = await api.get<{ results: Survey[] } | Survey[]>("/feedback/surveys/");
  return Array.isArray(res.data) ? res.data : res.data.results;
}

export async function saveSurvey(payload: Partial<Survey> & { id?: number }) {
  const { id, ...body } = payload;
  const res = id
    ? await api.patch<Survey>(`/feedback/surveys/${id}/`, body)
    : await api.post<Survey>("/feedback/surveys/", body);
  return res.data;
}

export async function deleteSurvey(id: number) {
  await api.delete(`/feedback/surveys/${id}/`);
}

export async function fetchPendingPrompts() {
  const res = await api.get<PendingPrompt[]>("/feedback/surveys/pending/");
  return res.data;
}

export async function submitResponse(payload: {
  survey: number;
  score: number;
  comment?: string;
  visit?: number | null;
  pt_session?: number | null;
}) {
  const res = await api.post("/feedback/responses/", payload);
  return res.data;
}

export async function fetchNps(params?: { from?: string; to?: string; survey?: number }) {
  const res = await api.get<NpsSummary>("/feedback/nps/", { params });
  return res.data;
}
