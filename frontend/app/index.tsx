import { useEffect } from 'react';
import { View, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';

import { useAuth } from '@/src/contexts/AuthContext';
import { tokens } from '@/src/theme/tokens';
import { resolveLifeSetupGate } from '@/src/life-setup/gate';

/**
 * Cold start entry — auth then Life Setup Gate.
 * Home is never the default for incomplete setup.
 */
export default function Index() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace('/login');
      return;
    }
    let cancelled = false;
    (async () => {
      const target = await resolveLifeSetupGate(user.user_id);
      if (cancelled) return;
      if (target === 'life-setup') {
        router.replace('/life-setup' as any);
      } else {
        router.replace('/(tabs)' as any);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loading, user, router]);

  return (
    <View
      testID="root-splash"
      style={{ flex: 1, backgroundColor: tokens.color.surface, alignItems: 'center', justifyContent: 'center' }}
    >
      <ActivityIndicator color={tokens.color.onSurfaceMuted} />
    </View>
  );
}
