import { useEffect, useState } from "react";
import { fetchMe, refresh } from "../api/auth";
import { useAuthStore } from "../store/authStore";

const COLD_START_HINT_MS = 3000;

/**
 * Runs once on app load: tries to silently mint a fresh access token from
 * the httpOnly refresh cookie (keeps a member logged in across reloads),
 * then loads /me. Also exposes a "slow" flag so the UI can show a
 * "waking up the server..." message instead of a bare spinner during a
 * Render free-tier cold start.
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
        const access = await refresh();
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
