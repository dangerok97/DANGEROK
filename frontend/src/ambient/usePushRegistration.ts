import { useEffect, useSyncExternalStore } from 'react';
import { AppState, Platform } from 'react-native';
import * as Notifications from 'expo-notifications';

import { useAuth } from '@/src/contexts/AuthContext';
import { pushLifecycle, reconcilePush, sessionCleanup } from './pushRegistration';

export function usePushRegistration() {
  return useSyncExternalStore(pushLifecycle.subscribe, pushLifecycle.getSnapshot, pushLifecycle.getSnapshot);
}
export function useSessionCleanup() {
  return useSyncExternalStore(sessionCleanup.subscribe, sessionCleanup.getSnapshot, sessionCleanup.getSnapshot);
}

/** Launch/foreground/token changes only reconcile permissions already given. */
export function usePushReconciliation(): void {
  const { user, loading } = useAuth();
  const push = usePushRegistration();
  const cleanup = useSessionCleanup();
  useEffect(() => {
    if (Platform.OS !== 'ios' && Platform.OS !== 'android') return;
    if (loading || !user?.user_id) return;
    const sync = () => { void reconcilePush(); };
    sync();
    const foreground = AppState.addEventListener('change', state => {
      if (state === 'active') sync();
    });
    const rotation = Notifications.addPushTokenListener(sync);
    return () => { foreground.remove(); rotation.remove(); };
  }, [loading, user?.user_id]);

  useEffect(() => {
    if (!user || push.state !== 'error') return;
    const timer = setInterval(() => {
      if (AppState.currentState === 'active') void reconcilePush();
    }, 15_000);
    return () => clearInterval(timer);
  }, [user, push.state]);

  // This lane remains alive on the login screen. A pending old-account
  // revocation never unregisters the native token of a newly signed-in user.
  useEffect(() => {
    void sessionCleanup.flush();
    const foreground = AppState.addEventListener('change', state => {
      if (state === 'active') void sessionCleanup.flush();
    });
    const online = () => { void sessionCleanup.flush(); };
    if (Platform.OS === 'web' && typeof window !== 'undefined') window.addEventListener('online', online);
    return () => {
      foreground.remove();
      if (Platform.OS === 'web' && typeof window !== 'undefined') window.removeEventListener('online', online);
    };
  }, []);
  useEffect(() => {
    if (!cleanup.pending && !cleanup.storageError) return;
    const timer = setInterval(() => {
      if (AppState.currentState === 'active') void sessionCleanup.flush();
    }, 15_000);
    return () => clearInterval(timer);
  }, [cleanup.pending, cleanup.storageError]);
}
