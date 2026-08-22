import { create } from "zustand";

export interface CurrentUser {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  is_staff: boolean;
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
export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  user: null,
  status: "idle",
  setAuth: (accessToken, user) => set({ accessToken, user, status: "ready" }),
  setAccessToken: (accessToken) => set({ accessToken }),
  setStatus: (status) => set({ status }),
  clear: () => set({ accessToken: null, user: null, status: "ready" }),
}));
