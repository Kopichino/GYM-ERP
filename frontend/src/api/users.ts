import { api } from "../lib/api";
import type { Role } from "../store/authStore";

export interface ManagedUser {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  role: Role;
  trainer: number | null;
  biometric_id: string | null;
}

export interface TrainerMember {
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

export async function fetchUsers(role?: Role) {
  const res = await api.get<{ results: ManagedUser[] }>("/auth/admin/users/", {
    params: role ? { role } : undefined,
  });
  return res.data.results;
}

export async function createUser(payload: Partial<ManagedUser> & { password?: string }) {
  const res = await api.post<ManagedUser>("/auth/admin/users/", payload);
  return res.data;
}

export async function updateUser(id: number, payload: Partial<ManagedUser> & { password?: string }) {
  const res = await api.patch<ManagedUser>(`/auth/admin/users/${id}/`, payload);
  return res.data;
}

export async function deleteUser(id: number) {
  await api.delete(`/auth/admin/users/${id}/`);
}

/** The signed-in trainer's own assigned roster. */
export async function fetchMyMembers() {
  const res = await api.get<{ results: TrainerMember[] }>("/auth/trainer/members/");
  return res.data.results;
}
