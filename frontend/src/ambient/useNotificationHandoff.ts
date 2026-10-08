/**
 * Native-only notification-tap handoff.
 *
 * A tap is not an approval of an ORA action: it may only acknowledge an
 * already-issued delivery plan and navigate to its backend-approved screen.
 * Permission requests and background reception do NOT happen here.
 */
import { useEffect, useRef } from 'react';
import { AppState, Platform } from 'react-native';
import { useRouter } from 'expo-router';

import { api } from '@/src/api/client';
import { useAuth } from '@/src/contexts/AuthContext';
import { parseNotificationHandoff } from './notificationHandoff';

export function useNotificationHandoff(): void {
  const { user, loading } = useAuth();
  const router = useRouter();
  const seen = useRef(new Set<string>());

  useEffect(() => {
    if (Platform.OS !== 'ios' && Platform.OS !== 'android') return;
    if (loading || !user?.user_id) return;

    const owner = user.user_id;
    let active = true;
    let cleanupListener: (() => void) | undefined;
    let cleanupForeground: (() => void) | undefined;
    let module: typeof import('expo-notifications') | undefined;

    const actOnResponse = async (
      response: import('expo-notifications').NotificationResponse | null,
    ) => {
      if (!response || !active) return;
      const data = response.notification.request.content.data;
      const handoff = parseNotificationHandoff(data);
      if (!handoff) return;
      const key = `${owner}:${response.notification.request.identifier}:${handoff.planId}`;
      if (seen.current.has(key)) return;
      seen.current.add(key);

      try {
        // This endpoint verifies that the plan actually belongs to the
        // signed-in account and was sent by Delivery. No cross-account route
        // is opened without that verified read/write.
        const result = await api.recordNotificationOpened(handoff.planId);
        if (result.ok && active) {
          router.push(handoff.route as any);
          await module?.clearLastNotificationResponseAsync();
        }
      } catch {
        // Offline is not proof that the notification was opened on the server.
        // Retrying at the next foreground will preserve the correct evidence.
        seen.current.delete(key);
      }
    };

    const pollLast = async () => {
      try {
        const response = await module?.getLastNotificationResponseAsync();
        if (active && response) await actOnResponse(response);
      } catch {
        // Native notification state can be unavailable on cold start.
      }
    };

    const install = async () => {
      const Notifications = await import('expo-notifications');
      if (!active) return;
      module = Notifications;
      const listener = Notifications.addNotificationResponseReceivedListener(
        response => { void actOnResponse(response); },
      );
      cleanupListener = () => listener.remove();
      const foreground = AppState.addEventListener('change', state => {
        if (state === 'active') void pollLast();
      });
      cleanupForeground = () => foreground.remove();
      void pollLast();
    };
    void install().catch(() => {});

    return () => {
      active = false;
      cleanupListener?.();
      cleanupForeground?.();
    };
  }, [loading, user?.user_id, router]);
}
