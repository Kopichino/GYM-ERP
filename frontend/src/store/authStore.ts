import { create } from "zustand";
import { queryClient } from "../lib/queryClient";

export type Role = "member" | "trainer" | "admin";

export interface CurrentUser {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  role: Role;
  is_staff: boolean;
}

/** Where an account lands after login, and where it is sent back to when it
 *  tries to open a portal it doesn't belong to. */
export function homePathFor(user: Pick<CurrentUser, "role"> | null) {
  if (user?.role === "admin") return "/admin";
  if (user?.role === "trainer") return "/trainer";
  return "/dashboard";
}

interface AuthState {
  accessToken: string | null;
  user: CurrentUser | null;
  status: "idle" | "checking" | "ready";
  setAuth: (accessToken: string, user: CurrentUser | null) => void;
  setAccessToken: (accessToken: string | null) => void;
  setStatus: (status: AuthState["status"]) => void;
  clear: () => void;
}

// Access token lives only in memory (this store), never localStorage --
// the refresh token that can mint new ones is an httpOnly cookie the JS
// layer never touches directly.
//
// The query cache belongs to whoever is signed in, so it is dropped here, the
// one place every sign-out goes through (Log out, and the forced sign-out when
// a refresh fails), and when a sign-in replaces a different signed-in user
// (/login is reachable while signed in). Without it an admin's member lists
// and plans stayed in memory and rendered for the next person on the tab. A
// token refresh keeps the same person and goes through setAccessToken, so it
// keeps the cache.
//
// Tabs of one browser share the refresh cookie but each keeps its own access
// token in memory. Signing out in one tab used to leave a second open tab
// signed in -- still showing the member list, and its token still accepted by
// the API for up to fifteen minutes. So every sign-out, and every sign-in, is
// announced to the other tabs: a sign-out ends their session too, and a sign-in
// as somebody else drops the previous person's session and data. Only the fact
// is sent, never a token.
type AuthBroadcast = { kind: "signed-out" } | { kind: "signed-in"; userId: number | null };

const channel: BroadcastChannel | null =
  typeof BroadcastChannel !== "undefined" ? new BroadcastChannel("ironcore-auth") : null;

function announce(message: AuthBroadcast) {
  try {
    channel?.postMessage(message);
  } catch {
    // A closed channel only means there is no other tab to tell.
  }
}

export const useAuthStore = create<AuthState>((set, get) => {
  /** Drop this tab's session. `tellOthers` is false when another tab told us. */
  function endSession(tellOthers: boolean) {
    // Nobody signed in means nothing private to drop -- and the start-up check
    // for a signed-out visitor lands here with public queries still loading.
    const signedIn = get().accessToken !== null || get().user !== null;
    set({ accessToken: null, user: null, status: "ready" });
    if (signedIn) {
      queryClient.clear();
      if (tellOthers) announce({ kind: "signed-out" });
    }
  }

  channel?.addEventListener("message", (event: MessageEvent<AuthBroadcast>) => {
    const message = event.data;
    if (message?.kind === "signed-out") endSession(false);
    const current = get().user;
    if (message?.kind === "signed-in" && current && current.id !== message.userId) endSession(false);
  });

  return {
    accessToken: null,
    user: null,
    status: "idle",
    setAuth: (accessToken, user) => {
      const previous = get().user;
      set({ accessToken, user, status: "ready" });
      if (previous && previous.id !== user?.id) queryClient.clear();
      announce({ kind: "signed-in", userId: user?.id ?? null });
    },
    setAccessToken: (accessToken) => set({ accessToken }),
    setStatus: (status) => set({ status }),
    clear: () => endSession(true),
  };
});
