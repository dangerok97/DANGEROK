import { useEffect } from 'react';
import { View, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';

import { useAuth } from '@/src/contexts/AuthContext';
import { tokens } from '@/src/theme/tokens';

export default function Index() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (user) router.replace('/(tabs)');
    else router.replace('/login');
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
