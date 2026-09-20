import { api } from "../lib/api";
import { fetchAll } from "../lib/pagination";

export interface Member {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  phone: string;
  join_date: string;
  membership_status: string;
  trainer: number | null;
  trainer_name: string | null;
  biometric_id: string | null;
  last_check_in: string | null;
  /** False for an account created without one -- imported members, mostly. */
  has_password: boolean;
  /** Whether they have an authenticator app set up for two-step sign-in. */
  has_mfa: boolean;
}

/**
 * Every member of this gym. The till's member picker and the Members page need
 * the whole list; reading only the first page left the 21st member unsellable.
 */
export async function fetchMembers() {
  return fetchAll<Member>("/auth/admin/members/");
}

export async function downloadMembersExcel() {
  const res = await api.get("/auth/admin/members/export/", { responseType: "blob" });
  const url = window.URL.createObjectURL(new Blob([res.data]));
  const link = document.createElement("a");
  link.href = url;
  link.setAttribute("download", "gym_members.xlsx");
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

/** Give a member of this gym a password -- for accounts created without one. */
export async function setMemberPassword(id: number, password: string) {
  await api.post(`/auth/admin/members/${id}/set-password/`, { password });
}
