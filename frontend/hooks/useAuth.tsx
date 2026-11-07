"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "@/services/api";
import type { User } from "@/types/api";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  can: (permission: string) => boolean;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState>({
  user: null, loading: true, login: async () => {}, logout: async () => {}, can: () => false, refresh: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const res = await api.get<User>("/auth/me");
      setUser(res.data);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const login = async (email: string, password: string) => {
    await api.post("/auth/login", { email, password });
    await refresh();
  };
  const logout = async () => {
    try { await api.post("/auth/logout"); } finally { setUser(null); }
  };
  const can = (permission: string) => !!user?.permissions && (user.permissions.includes("*") || user.permissions.includes(permission));

  return <AuthContext.Provider value={{ user, loading, login, logout, can, refresh }}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
