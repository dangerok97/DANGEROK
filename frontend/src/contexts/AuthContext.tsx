import React, { createContext, useContext, useEffect, useState, useSyncExternalStore } from 'react';
import { AppState, Platform } from 'react-native';
import { api, ApiUser, authToken } from '@/src/api/client';
import { openingSession } from '@/src/components/ora/presence/openingSession';
import { activatePushSession, endPushSession } from '@/src/ambient/pushRegistration';
import { createSessionLifecycle } from '@/src/auth/sessionLifecycle';

type AuthState = {
  user: ApiUser | null;
  loading: boolean;
  refreshing: boolean;
  recovery: boolean;
  signIn: (token: string, user: ApiUser) => Promise<void>;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
  updateUser: (user: ApiUser) => void;
};

const Ctx = createContext<AuthState>({
  user: null, loading: true, refreshing: false, recovery: false,
  signIn: async () => {}, signOut: async () => {}, refresh: async () => {}, updateUser: () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [lifecycle] = useState(() => createSessionLifecycle<ApiUser>({
    readToken: authToken.get, writeToken: authToken.set, clearToken: authToken.clear,
    me: token => api.me(token),
    activate: (token, user) => activatePushSession({ ownerId: user.user_id, token }),
    end: async token => {
      await endPushSession(token);
      // Location monitoring belongs to the same signed-in person too.
      try {
        const runtime = await import('@/src/location/presenceRuntime');
        await runtime.shutdown();
      } catch { /* A stopped native runtime must not prevent local logout. */ }
    },
    resetOpening: () => openingSession.reset(),
  }));
  const state = useSyncExternalStore(lifecycle.subscribe, lifecycle.getSnapshot, lifecycle.getSnapshot);

  useEffect(() => {
    void lifecycle.refresh();
    const foreground = AppState.addEventListener('change', status => {
      if (status === 'active') void lifecycle.refresh();
    });
    const online = () => { void lifecycle.refresh(); };
    if (Platform.OS === 'web' && typeof window !== 'undefined') window.addEventListener('online', online);
    return () => {
      foreground.remove();
      if (Platform.OS === 'web' && typeof window !== 'undefined') window.removeEventListener('online', online);
    };
  }, [lifecycle]);
  useEffect(() => {
    if (!state.recovery) return;
    const timer = setInterval(() => {
      if (AppState.currentState === 'active') void lifecycle.refresh();
    }, 15_000);
    return () => clearInterval(timer);
  }, [lifecycle, state.recovery]);

  return <Ctx.Provider value={{
    ...state, signIn: lifecycle.signIn, signOut: lifecycle.signOut,
    refresh: lifecycle.refresh, updateUser: lifecycle.updateUser,
  }}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);
