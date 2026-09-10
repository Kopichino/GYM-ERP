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
  "/auth/signup/",
  "/auth/login/",
  "/auth/refresh/",
  "/auth/logout/",
  "/auth/me/",
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

async function refreshAccessToken(): Promise<string | null> {
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

interface RetriableConfig extends InternalAxiosRequestConfig {
  _retried?: boolean;
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as RetriableConfig | undefined;
    if (error.response?.status === 401 && original && !original._retried) {
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
