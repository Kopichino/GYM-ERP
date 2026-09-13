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
  /** A friend's code. Ignored if it doesn't match anyone -- signing up never
      fails because someone mistyped a code they were given. */
  referral_code?: string;
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

/** Resolves the same way whether or not the email has an account. */
export async function requestPasswordReset(email: string) {
  await api.post("/auth/password/forgot/", { email });
}

export async function resetPassword(payload: { uid: string; token: string; password: string }) {
  await api.post("/auth/password/reset/", payload);
}

/**
 * Change your own password. Resolves to a fresh access token: the server ends
 * every session, this one included, then re-issues this one so the page you
 * changed it on stays signed in.
 */
export async function changePassword(payload: {
  current_password: string;
  new_password: string;
}) {
  const res = await api.post<{ access: string }>("/auth/password/change/", payload);
  return res.data.access;
}
