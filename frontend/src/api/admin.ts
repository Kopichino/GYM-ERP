import { api } from "../lib/api";

export interface Member {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  phone: string;
  join_date: string;
  membership_status: string;
  last_check_in: string | null;
}

export async function fetchMembers() {
  const res = await api.get<{ results: Member[] }>("/auth/admin/members/");
  return res.data.results;
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
