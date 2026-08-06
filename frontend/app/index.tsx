import { useEffect } from 'react';
import { View, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';

import { useAuth } from '@/src/contexts/AuthContext';
import { api } from '@/src/api/client';
import { tokens } from '@/src/theme/tokens';

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
      try {
        const st = await api.lifeSetupStatus();
        if (cancelled) return;
        // First-launch conversation only — never a permanent Life Setup section
        if (st.ok && st.should_show && st.module_visible === false) {
          router.replace('/life-setup' as any);
          return;
        }
      } catch {
        // Fail soft → Home
      }
      if (!cancelled) router.replace('/(tabs)');
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
