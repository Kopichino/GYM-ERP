import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";
import { useAuthStore } from "../store/authStore";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api";

/**
 * Which gym this portal is for.
 *
 * Interim: the backend reads the tenant from a `/t/<slug>/` prefix while every
 * gym is still on one hostname. When custom domains land, the server resolves
 * the tenant from the host instead and this becomes an empty string — which is
 * why it is prepended in one place rather than baked into every call site.
 */
const TENANT_SLUG = import.meta.env.VITE_TENANT_SLUG ?? "ironcore-main";

/**
 * The only routes that are about the person rather than about a gym.
 *
 * Signing in happens before there is a gym to sign in to, and the token
 * identifies a person who may belong to several. Everything else is a question
 * about one gym and carries its prefix.
 *
 * An exact list rather than a `/auth/` prefix match, because the auth app also
 * serves `/auth/admin/members/` and `/auth/trainer/members/`, which are very
 * much about one gym. Excluding all of `/auth/` sent those unprefixed and the
 * trainer portal showed "no members assigned to you".
 */
const PLATFORM_ROUTES = [
  // Not /auth/signup/: signing up is joining one particular gym, so it carries
  // that gym's prefix like everything else. Sent unprefixed it resolved no gym,
  // and the new account was created with standing nowhere -- it could log in
  // and see nothing, and a referral code crashed it outright.
  "/auth/login/",
  "/auth/refresh/",
  "/auth/logout/",
  "/auth/me/",
  // Forgetting, resetting and changing a password are about the person's
  // account, which spans every gym they belong to.
  "/auth/password/",
  // Two-step sign-in is part of signing in, and belongs to the person as well.
  "/auth/mfa/",
];

function isPlatformRoute(path: string) {
  return PLATFORM_ROUTES.some((route) => path.startsWith(route));
}

/**
 * The absolute URL for a route, tenant prefix included.
 *
 * Every in-app call goes through the interceptor below and stays relative. This
 * exists for the one place that cannot: the snippet a gym pastes into their own
 * website, which runs on their server and needs a real address. Built from the
 * same two constants so it cannot drift from what the app itself calls.
 */
export function absoluteUrl(path: string) {
  const base = TENANT_SLUG ? `${API_URL}/t/${TENANT_SLUG}` : API_URL;
  return `${base}${path}`;
}

export const api = axios.create({
  baseURL: API_URL,
  withCredentials: true, // sends the httpOnly refresh cookie
});

api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  const path = config.url ?? "";
  if (TENANT_SLUG && !isPlatformRoute(path) && !path.startsWith("/t/")) {
    config.url = `/t/${TENANT_SLUG}${path.startsWith("/") ? "" : "/"}${path}`;
  }
  return config;
});

let refreshPromise: Promise<string | null> | null = null;

/**
 * A new access token from the refresh cookie, or null.
 *
 * One request however many callers ask at once: the app's start-up check (which
 * React's StrictMode runs twice in development) and every request that has just
 * been answered 401 all wait on the same call.
 */
export async function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = axios
      .post<{ access: string }>(`${API_URL}/auth/refresh/`, null, { withCredentials: true })
      .then((res) => res.data.access)
      .catch(() => null)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

/**
 * Requests whose 401 means "that sign-in attempt failed", not "the access token
 * has expired". Refreshing and retrying can never rescue one, and doing it cost
 * an extra refresh on every failed login and every signed-out page load.
 */
const SIGN_IN_ROUTES = [
  "/auth/refresh/",
  "/auth/login/",
  "/auth/signup/",
  "/auth/mfa/login/",
  "/auth/password/forgot/",
  "/auth/password/reset/",
];

function isSignInRequest(url: string | undefined) {
  return SIGN_IN_ROUTES.some((route) => (url ?? "").includes(route));
}

interface RetriableConfig extends InternalAxiosRequestConfig {
  _retried?: boolean;
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as RetriableConfig | undefined;
    if (
      error.response?.status === 401 &&
      original &&
      !original._retried &&
      !isSignInRequest(original.url)
    ) {
      original._retried = true;
      const newAccess = await refreshAccessToken();
      if (newAccess) {
        useAuthStore.getState().setAccessToken(newAccess);
        original.headers = original.headers ?? {};
        original.headers.Authorization = `Bearer ${newAccess}`;
        return api(original);
      }
      useAuthStore.getState().clear();
    }
    return Promise.reject(error);
  }
);
