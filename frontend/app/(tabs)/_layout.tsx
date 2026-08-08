import { useEffect } from 'react';
import { Tabs, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Platform, StyleSheet, View } from 'react-native';
import { BlurView } from 'expo-blur';
import * as Haptics from 'expo-haptics';

import { tokens } from '@/src/theme/tokens';
import { useAuth } from '@/src/contexts/AuthContext';
import { resolveLifeSetupGate } from '@/src/life-setup/gate';

function TabBarBackground() {
  if (Platform.OS === 'ios') {
    return (
      <BlurView
        tint="dark"
        intensity={80}
        style={[StyleSheet.absoluteFill, { backgroundColor: 'rgba(10,10,10,0.55)' }]}
      />
    );
  }
  return <View style={[StyleSheet.absoluteFill, { backgroundColor: 'rgba(12,12,12,0.96)' }]} />;
}

/**
 * Tabs shell — UI unchanged. Gate only: incomplete Life Setup cannot stay on Home/tabs.
 */
export default function TabsLayout() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading || !user?.user_id) return;
    let cancelled = false;
    (async () => {
      const target = await resolveLifeSetupGate(user.user_id);
      if (!cancelled && target === 'life-setup') {
        router.replace('/life-setup' as any);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loading, user?.user_id, router]);

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: tokens.color.onSurface,
        tabBarInactiveTintColor: tokens.color.onSurfaceDim,
        tabBarStyle: {
          position: 'absolute',
          borderTopColor: tokens.color.border,
          borderTopWidth: StyleSheet.hairlineWidth,
          backgroundColor: 'transparent',
          elevation: 0,
        },
        tabBarBackground: () => <TabBarBackground />,
        tabBarLabelStyle: { fontSize: 11, fontWeight: '500' },
      }}
      screenListeners={{
        tabPress: () => {
          if (Platform.OS !== 'web') Haptics.selectionAsync();
        },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Home',
          tabBarIcon: ({ color, size }) => <Ionicons name="ellipse-outline" size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="memoria"
        options={{
          title: 'Memoria',
          tabBarIcon: ({ color, size }) => <Ionicons name="search-outline" size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="documenti"
        options={{
          title: 'Documenti',
          tabBarIcon: ({ color, size }) => <Ionicons name="document-text-outline" size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="aggiungi"
        options={{
          title: 'Aggiungi',
          tabBarIcon: ({ color, size }) => <Ionicons name="add-circle-outline" size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="profilo"
        options={{
          title: 'Profilo',
          tabBarIcon: ({ color, size }) => <Ionicons name="person-outline" size={size} color={color} />,
        }}
      />
    </Tabs>
  );
}
