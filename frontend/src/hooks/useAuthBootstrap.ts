import { useEffect, useState } from "react";
import { fetchMe } from "../api/auth";
import { refreshAccessToken } from "../lib/api";
import { useAuthStore } from "../store/authStore";

const COLD_START_HINT_MS = 3000;

/**
 * Runs once on app load: tries to silently mint a fresh access token from
 * the httpOnly refresh cookie (keeps a member logged in across reloads),
 * then loads /me. Also exposes a "slow" flag so the UI can show a
 * "waking up the server..." message instead of a bare spinner during a
 * Render free-tier cold start.
 *
 * The refresh goes through `refreshAccessToken`, which shares one in-flight
 * request between callers. This effect runs twice under StrictMode in
 * development, and each run used to send its own refresh -- which the 401
 * retry in `lib/api` then sent again.
 */
export function useAuthBootstrap() {
  const status = useAuthStore((s) => s.status);
  const setAuth = useAuthStore((s) => s.setAuth);
  const clear = useAuthStore((s) => s.clear);
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const slowTimer = setTimeout(() => {
      if (!cancelled) setSlow(true);
    }, COLD_START_HINT_MS);

    (async () => {
      try {
        const access = await refreshAccessToken();
        if (cancelled) return;
        if (!access) {
          clear();
          return;
        }
        useAuthStore.getState().setAccessToken(access);
        const user = await fetchMe();
        if (!cancelled) setAuth(access, user);
      } catch {
        if (!cancelled) clear();
      } finally {
        clearTimeout(slowTimer);
      }
    })();

    return () => {
      cancelled = true;
      clearTimeout(slowTimer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { ready: status === "ready", slow: slow && status !== "ready" };
}
