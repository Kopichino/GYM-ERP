type ApiError = { response?: { status?: number; data?: Record<string, unknown> } };

/**
 * The machine-readable reason a two-step request was refused, when it gave one.
 * `mfa_token_invalid` means the sign-in has to start again from the password.
 */
export function mfaReason(err: unknown): string | undefined {
  const reason = (err as ApiError)?.response?.data?.reason;
  return typeof reason === "string" ? reason : undefined;
}

/** The sentence to show for a failed two-step request. */
export function mfaErrorMessage(err: unknown, fallback: string): string {
  const response = (err as ApiError)?.response;
  if (response?.status === 429) return "Too many attempts. Wait a minute, then try again.";
  const data = response?.data ?? {};
  for (const field of ["code", "recovery_code", "password"]) {
    const value = data[field];
    if (Array.isArray(value) && value.length) return value.join(" ");
  }
  return typeof data.detail === "string" ? data.detail : fallback;
}
