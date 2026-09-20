import { api } from "../lib/api";

/** A membership plan as the public website shows it. The same row the admin
 *  edits on the Plans page, so a price change there is on the website at once. */
export interface PublicPlan {
  id: number;
  name: string;
  price: string;
  duration_days: number;
  description: string;
}

/** Readable signed out: the website is for people who are not members yet. */
export async function fetchPublicPlans() {
  const res = await api.get<PublicPlan[]>("/billing/public/plans/");
  return res.data;
}
