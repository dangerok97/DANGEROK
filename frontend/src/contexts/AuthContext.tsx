import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { api, ApiUser, authToken } from '@/src/api/client';

type AuthState = {
  user: ApiUser | null;
  loading: boolean;
  signIn: (token: string, user: ApiUser) => Promise<void>;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
};

const Ctx = createContext<AuthState>({
  user: null,
  loading: true,
  signIn: async () => {},
  signOut: async () => {},
  refresh: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<ApiUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const t = await authToken.get();
      if (!t) {
        setUser(null);
        return;
      }
      const u = await api.me();
      setUser(u);
    } catch {
      await authToken.clear();
      setUser(null);
    }
  }, []);

  useEffect(() => {
    (async () => {
      await refresh();
      setLoading(false);
    })();
  }, [refresh]);

  const signIn = useCallback(async (token: string, u: ApiUser) => {
    await authToken.set(token);
    setUser(u);
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } catch {}
    await authToken.clear();
    setUser(null);
  }, []);

  return <Ctx.Provider value={{ user, loading, signIn, signOut, refresh }}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);
