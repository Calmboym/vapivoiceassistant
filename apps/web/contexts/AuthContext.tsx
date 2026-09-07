"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, ApiRequestError } from "@/lib/api";

export type CurrentUser = {
  id: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
  phone: string | null;
  status: string;
  email_verified: boolean;
  roles: string[];
  permissions: string[];
  created_at: string;
};

type AuthState = {
  user: CurrentUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (input: { email: string; password: string; first_name?: string; last_name?: string }) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

// This context is a UX convenience — it caches what /auth/me said so the
// UI doesn't flash a logged-out state on every navigation. It is NOT the
// source of truth for authorization: every request that actually needs
// to be authorized is re-checked server-side, from the session cookie,
// on that request (§35). A stale/tampered value here can make the UI
// show the wrong button; it cannot make the backend do the wrong thing.
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  const loadMe = useCallback(async () => {
    try {
      const me = await api.get<CurrentUser>("/api/v1/auth/me");
      setUser(me);
    } catch (err) {
      if (err instanceof ApiRequestError && (err.status === 401 || err.status === 403)) {
        setUser(null);
      } else {
        // Network/unexpected error — don't confidently claim "logged
        // out" here; just leave the previous state and let the next
        // authenticated request surface the real error.
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMe();
  }, [loadMe]);

  const login = useCallback(async (email: string, password: string) => {
    const me = await api.post<CurrentUser>("/api/v1/auth/login", { email, password });
    setUser(me);
  }, []);

  const register = useCallback(
    async (input: { email: string; password: string; first_name?: string; last_name?: string }) => {
      const me = await api.post<CurrentUser>("/api/v1/auth/register", input);
      setUser(me);
    },
    []
  );

  const logout = useCallback(async () => {
    await api.post("/api/v1/auth/logout");
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, register, logout, refresh: loadMe }),
    [user, loading, login, register, logout, loadMe]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth() must be used inside <AuthProvider>");
  return ctx;
}
