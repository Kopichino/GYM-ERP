type ApiError = { response?: { data?: Record<string, unknown> } } | null;

/**
 * The server's own words for a refusal -- its `detail`, or the message on the
 * first field it objected to -- or `fallback` when it gave none.
 */
export function serverMessage(err: unknown, fallback: string) {
  const data = (err as ApiError)?.response?.data;
  if (!data) return fallback;
  const value = data.detail ?? Object.values(data)[0];
  const message = Array.isArray(value) ? value[0] : value;
  return typeof message === "string" && message ? message : fallback;
}
