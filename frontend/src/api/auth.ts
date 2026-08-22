import { api } from "../lib/api";
import type { CurrentUser } from "../store/authStore";

export interface LoginPayload {
  username: string;
  password: string;
}

export interface SignupPayload {
  username: string;
  email: string;
  password: string;
  first_name?: string;
  last_name?: string;
}

export async function login(payload: LoginPayload) {
  const res = await api.post<{ access: string }>("/auth/login/", payload);
  return res.data.access;
}

export async function signup(payload: SignupPayload) {
  await api.post("/auth/signup/", payload);
}

export async function refresh() {
  const res = await api.post<{ access: string }>("/auth/refresh/", null);
  return res.data.access;
}

export async function logout() {
  await api.post("/auth/logout/");
}

export async function fetchMe() {
  const res = await api.get<CurrentUser>("/auth/me/");
  return res.data;
}
