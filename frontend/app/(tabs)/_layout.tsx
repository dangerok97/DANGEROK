import { useEffect } from 'react';
import { Tabs, useRouter } from 'expo-router';

import { useAuth } from '@/src/contexts/AuthContext';
import { resolveLifeSetupGate } from '@/src/life-setup/gate';
import { AmbientTabBar, AMBIENT_RAIL_WIDTH } from '@/src/shell';
import { useBreakpoint } from '@/src/theme/responsive';
import { useTheme } from '@/src/theme/ThemeProvider';

/**
 * Ambient shell — IA 2.0: Home · Vita · ORA · Attività · Documenti, with
 * account set apart. Memoria and Aggiungi remain routes (href:null) reachable
 * from Profilo — Memoria is a trust surface you visit to check what ORA knows,
 * not a daily destination. Life Setup gate unchanged.
 */
export default function TabsLayout() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const bp = useBreakpoint();
  const { colors } = useTheme();
  const isRail = bp === 'desktop';

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
      tabBar={(props) => <AmbientTabBar {...props} />}
      screenOptions={{
        headerShown: false,
        // Desktop breakpoint → left rail; phone/tablet → floating bottom
        tabBarPosition: isRail ? 'left' : 'bottom',
        // Width must match AmbientTabBar railWrap (no flex:1) — scene gets remaining viewport
        tabBarStyle: isRail
          ? {
              width: AMBIENT_RAIL_WIDTH,
              maxWidth: AMBIENT_RAIL_WIDTH,
              backgroundColor: colors.backgroundSecondary,
              borderTopWidth: 0,
              borderRightWidth: 0,
              elevation: 0,
            }
          : {
              position: 'absolute',
              backgroundColor: 'transparent',
              borderTopWidth: 0,
              elevation: 0,
              height: 0,
            },
      }}
    >
      <Tabs.Screen name="index" options={{ title: 'Home' }} />
      <Tabs.Screen name="contesti" options={{ title: 'Vita' }} />
      {/*
        ORA is a destination, and its surface is the conversation at `/ora` —
        not this screen, which was a second, thinner entry page sharing the
        same address. The bar pushes the real one; this stays out of the
        navigation so the address means one thing.
      */}
      <Tabs.Screen name="ora" options={{ title: 'ORA', href: null }} />
      <Tabs.Screen name="attivita" options={{ title: 'Attività' }} />
      <Tabs.Screen name="documenti" options={{ title: 'Documenti' }} />
      {/*
        Five destinations, and Profilo is not one of them. It keeps living
        under `(tabs)` because moving the route would buy nothing and risk the
        deep links that already point at it; `href: null` is what takes it out
        of the navigation without touching the URL anyone may have saved.
      */}
      <Tabs.Screen name="profilo" options={{ title: 'Profilo', href: null }} />
      <Tabs.Screen
        name="memoria"
        options={{
          title: 'Memoria',
          href: null,
        }}
      />
      <Tabs.Screen
        name="aggiungi"
        options={{
          title: 'Aggiungi',
          href: null,
        }}
      />
    </Tabs>
  );
}
