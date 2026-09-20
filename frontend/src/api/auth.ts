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

/**
 * What a correct password gets you.
 *
 * A session straight away only where two-step sign-in is not required and the
 * account has not set it up. Otherwise a short-lived token that stands in for
 * the password while the second step is done: `mfa` when a code is due,
 * `mfa_setup` when the account has never set up an authenticator.
 */
export type LoginResult =
  | { kind: "session"; access: string }
  | { kind: "mfa" | "mfa_setup"; mfaToken: string };

interface LoginResponse {
  access?: string;
  mfa_required?: boolean;
  mfa_setup_required?: boolean;
  mfa_token?: string;
}

export async function login(payload: LoginPayload): Promise<LoginResult> {
  const { data } = await api.post<LoginResponse>("/auth/login/", payload);
  if (data.mfa_token) {
    return { kind: data.mfa_setup_required ? "mfa_setup" : "mfa", mfaToken: data.mfa_token };
  }
  return { kind: "session", access: data.access ?? "" };
}

export async function signup(payload: SignupPayload) {
  await api.post("/auth/signup/", payload);
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

// ---------------------------------------------------------------- two-step sign-in

/** The key for a new authenticator app: as a QR-code link, and as text to type. */
export interface MfaSetup {
  secret: string;
  otpauth_uri: string;
  issuer: string;
  account_name: string;
}

export interface MfaStatus {
  enabled: boolean;
  confirmed_at: string | null;
  recovery_codes_remaining: number;
  required: boolean;
}

/** Step two of signing in: a code from the app, or one recovery code. */
export async function verifyMfa(payload: {
  mfa_token: string;
  code?: string;
  recovery_code?: string;
}) {
  const res = await api.post<{
    access: string;
    used_recovery_code?: boolean;
    recovery_codes_remaining?: number;
  }>("/auth/mfa/login/verify/", payload);
  return res.data;
}

/** Signing in without an authenticator yet: the key to add. Asking twice returns the same key. */
export async function startSignInMfaSetup(mfaToken: string) {
  const res = await api.post<MfaSetup>("/auth/mfa/login/setup/", { mfa_token: mfaToken });
  return res.data;
}

/**
 * Finishes setup while signing in. Opens the session, and returns the recovery
 * codes -- the only time they are ever readable.
 */
export async function confirmSignInMfaSetup(mfaToken: string, code: string) {
  const res = await api.post<{ access: string; recovery_codes: string[] }>(
    "/auth/mfa/login/confirm/",
    { mfa_token: mfaToken, code },
  );
  return res.data;
}

export async function fetchMfaStatus() {
  const res = await api.get<MfaStatus>("/auth/mfa/");
  return res.data;
}

/** Start moving to a new phone. Needs the password, like changing it does. */
export async function startMfaSetup(password: string) {
  const res = await api.post<MfaSetup>("/auth/mfa/setup/", { password });
  return res.data;
}

/**
 * Finish moving to a new phone. Every other session ends, and this one is
 * re-issued -- so it resolves to a fresh access token with the new codes.
 */
export async function confirmMfaSetup(code: string) {
  const res = await api.post<{ access: string; recovery_codes: string[] }>("/auth/mfa/confirm/", {
    code,
  });
  return res.data;
}

/** A new set of recovery codes, replacing the old set. Needs a current code. */
export async function regenerateRecoveryCodes(code: string) {
  const res = await api.post<{ recovery_codes: string[] }>("/auth/mfa/recovery-codes/", { code });
  return res.data;
}
