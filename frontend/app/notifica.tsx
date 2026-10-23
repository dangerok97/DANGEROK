/**
 * Where a tapped web notification lands.
 *
 * The service worker passes the delivery plan and the route it carried. As on
 * the phone app, a tap is not an approval of anything: the plan is
 * acknowledged on the server, which returns its own route, and the two must
 * agree before ORA opens it. Anything else lands on Home.
 */
import { useEffect } from 'react';
import { ActivityIndicator, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';

import { api } from '@/src/api/client';
import { canonicalNotificationRoute, parseNotificationHandoff } from '@/src/ambient/notificationHandoff';
import { useAuth } from '@/src/contexts/AuthContext';
import { useTheme } from '@/src/theme/ThemeProvider';

export default function NotificaScreen() {
  const { p, to } = useLocalSearchParams<{ p?: string; to?: string }>();
  const { user, loading } = useAuth();
  const router = useRouter();
  const { colors } = useTheme();

  useEffect(() => {
    if (loading || !user) return;
    let active = true;
    const handoff = parseNotificationHandoff({ plan_id: p, deep_link: to });
    const go = (route: string) => { if (active) router.replace(route as any); };
    if (!handoff || handoff.planId.startsWith('dlv_test')) {
      go('/');
      return () => { active = false; };
    }
    api.recordNotificationOpened(handoff.planId)
      .then(reply => go(canonicalNotificationRoute(handoff, reply) || '/'))
      .catch(() => go('/'));
    return () => { active = false; };
  }, [loading, user, p, to, router]);

  return (
    <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.backgroundPrimary }}>
      <ActivityIndicator />
    </View>
  );
}
