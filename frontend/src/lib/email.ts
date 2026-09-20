/** Word for word what the API says about a malformed address. */
export const INVALID_EMAIL = "Enter a valid email address.";

/**
 * Whether `value` is shaped like an email address: something, an @, and a domain
 * with a dot. Deliberately loose -- it catches typing mistakes before a round
 * trip, and the server's own check stays the one that decides.
 */
export function looksLikeEmail(value: string) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}
