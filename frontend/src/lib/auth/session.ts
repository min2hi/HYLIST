/**
 * Auth Session Management (Zustand)
 *
 * Lưu JWT token trong memory (Zustand) + cookie (persist qua refresh).
 * KHÔNG dùng localStorage vì dễ bị XSS.
 * Cookie được set với httpOnly=false (JS readable) vì Next.js middleware cần đọc.
 * Trong production thực tế: dùng httpOnly cookie set bởi backend /auth/refresh.
 */
import Cookies from "js-cookie";
import { create } from "zustand";

const TOKEN_COOKIE = "hylist_token";
const COOKIE_EXPIRES = 7; // days

interface User {
  id: string;
  email: string;
  full_name: string;
  role: "ADMIN" | "MANAGER" | "MEMBER" | "VIEWER";
  org_id: string;
}

interface AuthState {
  token: string | null;
  user: User | null;
  isAuthenticated: boolean;

  // Actions
  setAuth: (token: string, user: User) => void;
  logout: () => void;
  initFromCookie: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  user: null,
  isAuthenticated: false,

  setAuth: (token, user) => {
    Cookies.set(TOKEN_COOKIE, token, {
      expires: COOKIE_EXPIRES,
      sameSite: "lax",
    });
    set({ token, user, isAuthenticated: true });
  },

  logout: () => {
    Cookies.remove(TOKEN_COOKIE);
    set({ token: null, user: null, isAuthenticated: false });
  },

  initFromCookie: () => {
    const token = Cookies.get(TOKEN_COOKIE);
    if (token) {
      // Decode JWT payload (khong verify — chỉ đọc user info)
      try {
        const payload = JSON.parse(atob(token.split(".")[1]));
        const user: User = {
          id: payload.sub,
          email: payload.email,
          full_name: payload.full_name,
          role: payload.role,
          org_id: payload.org_id,
        };
        set({ token, user, isAuthenticated: true });
      } catch {
        Cookies.remove(TOKEN_COOKIE);
      }
    }
  },
}));

/** Lấy token hiện tại cho SSE query param */
export const getToken = (): string | null => {
  return useAuthStore.getState().token ?? Cookies.get(TOKEN_COOKIE) ?? null;
};
