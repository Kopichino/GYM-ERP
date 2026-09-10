import { api } from "../lib/api";

export type LeadFailureReason =
  | "revoked"
  | "origin"
  | "suspended"
  | "payload"
  | "rate";

/**
 * What went wrong, and what the owner should do about it.
 *
 * Paired deliberately: "blocked by the allowed-addresses list" is a diagnosis,
 * not an instruction, and the person reading it runs a gym rather than a
 * webserver. Each one names the consequence -- enquiries being lost -- because
 * that is what makes it worth acting on today rather than next month.
 */
export const LEAD_FAILURE_HELP: Record<
  LeadFailureReason,
  { headline: string; advice: string }
> = {
  revoked: {
    headline: "Your website is still using a key you revoked.",
    advice:
      "Every enquiry it sends is being lost. Issue a new key below and paste the new form code into your site.",
  },
  origin: {
    headline: "Submissions are coming from an address this key does not allow.",
    advice:
      "Add the address your form actually runs on to this key's allowed list, or clear the list to accept any address.",
  },
  suspended: {
    headline: "This gym is not currently accepting enquiries.",
    advice: "Your website form will keep being turned away until that changes.",
  },
  payload: {
    headline: "Your form is sending submissions with no name or contact details.",
    advice:
      "If the form code was edited, check the boxes are still named name, phone, email and message. Nothing sent this way reaches your pipeline.",
  },
  rate: {
    headline: "This key hit its limit of 30 submissions in an hour.",
    advice:
      "Genuine enquiries in that hour were turned away. If it was a bot, revoke this key and issue a new one.",
  },
};

export interface LeadApiKey {
  id: number;
  label: string;
  /** One origin per line. Empty means the key works from anywhere. */
  allowed_origins: string;
  is_active: boolean;
  last_used_at: string | null;
  leads_created: number;
  created_at: string;
  /** Why the last refused submission was refused. Empty if none ever was. */
  last_failure_reason: LeadFailureReason | "";
  last_failure_at: string | null;
  /**
   * Bursts of failure since the last accepted lead. Any accepted lead resets
   * it, so a form that has been fixed stops warning on its own.
   */
  failures_since_success: number;
  /**
   * Only ever present on the response to a create. The server stores a hash,
   * so this is the one moment the key exists outside the gym's own site.
   */
  plaintext?: string;
}

export async function fetchLeadKeys() {
  const res = await api.get<{ results: LeadApiKey[] }>("/tenancy/lead-keys/");
  return res.data.results;
}

export async function createLeadKey(payload: {
  label: string;
  allowed_origins: string;
}) {
  const res = await api.post<LeadApiKey>("/tenancy/lead-keys/", payload);
  return res.data;
}

/** Revoking is an update, not a delete — the usage trail outlives the key. */
export async function revokeLeadKey(id: number) {
  const res = await api.patch<LeadApiKey>(`/tenancy/lead-keys/${id}/`, {
    is_active: false,
  });
  return res.data;
}

export async function deleteLeadKey(id: number) {
  await api.delete(`/tenancy/lead-keys/${id}/`);
}
