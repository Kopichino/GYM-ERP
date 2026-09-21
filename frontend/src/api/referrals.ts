import { api } from "../lib/api";

export type ReferralStatus = "pending" | "signed_up" | "joined";

export interface ReferralReward {
  id: number;
  referral: number;
  days_granted: number;
  payment: number | null;
  granted_by: number | null;
  granted_by_name: string | null;
  granted_on: string;
  notes: string;
}

export interface Referral {
  id: number;
  referrer: number;
  referrer_name: string;
  name: string;
  phone: string;
  email: string;
  referred_user: number | null;
  referred_username: string | null;
  enquiry: number | null;
  /** Derived from the ledger, so a refund walks it back on its own. */
  status: ReferralStatus;
  is_rewardable: boolean;
  reward: ReferralReward | null;
  notes: string;
  created_at: string;
}

export interface MyReferrals {
  code: string;
  blurb: string;
  reward_days: number;
  program_active: boolean;
  total_referred: number;
  joined_count: number;
  days_earned: number;
  referrals: Referral[];
}

export interface ReferralProgram {
  id: number;
  reward_days: number;
  blurb: string;
  is_active: boolean;
  updated_at: string;
}

export async function fetchMyReferrals() {
  const res = await api.get<MyReferrals>("/referrals/mine/");
  return res.data;
}

export async function createReferral(payload: {
  name: string;
  phone?: string;
  email?: string;
  notes?: string;
}) {
  const res = await api.post<Referral>("/referrals/", payload);
  return res.data;
}

export async function fetchReferrals() {
  const res = await api.get<{ results: Referral[] }>("/referrals/");
  return res.data.results;
}

export async function rewardReferral(id: number, days?: number) {
  const res = await api.post<Referral>(`/referrals/${id}/reward/`, days ? { days } : {});
  return res.data;
}

export async function fetchReferralPrograms() {
  const res = await api.get<{ results: ReferralProgram[] }>("/referrals/programs/");
  return res.data.results;
}

export async function createReferralProgram(payload: { reward_days: number; blurb: string }) {
  const res = await api.post<ReferralProgram>("/referrals/programs/", payload);
  return res.data;
}

/** Changes an offer in place -- how the running offer is edited. */
export async function updateReferralProgram(
  id: number,
  payload: Partial<{ reward_days: number; blurb: string; is_active: boolean }>,
) {
  const res = await api.patch<ReferralProgram>(`/referrals/programs/${id}/`, payload);
  return res.data;
}
