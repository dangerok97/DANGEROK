import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';
import { AppState, LogBox, Platform, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { GestureHandlerRootView } from 'react-native-gesture-handler';

import { useIconFonts } from '@/src/hooks/use-icon-fonts';
import { AuthProvider } from '@/src/contexts/AuthContext';
import { ThemeProvider, useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { AuthGate, ShellModeProvider, useShellTransitionMs } from '@/src/shell';
import { installWebGlobals } from '@/src/theme/webGlobals';

/*
  The background task has to be defined at module scope, before the OS ever
  asks for it: a phone woken by a geofence loads the JS bundle and looks for a
  task with that name, and a definition inside a component would not exist yet.
  Native only — the web bundle must not pull expo-task-manager in at all.
*/
if (Platform.OS === 'ios' || Platform.OS === 'android') {
  require('@/src/location/presenceTask');
}

LogBox.ignoreAllLogs(true);
SplashScreen.preventAutoHideAsync();

/**
 * One fix and a flush whenever ORA comes to the front.
 *
 * The stored presence state is a belief, and beliefs go stale: phones get
 * switched off, background tasks get killed, callbacks never arrive. Without
 * this, "sei a casa" survives into an airport.
 */
function usePresenceReconciliation() {
  useEffect(() => {
    if (Platform.OS !== 'ios' && Platform.OS !== 'android') return undefined;

    const catchUp = () => {
      void (async () => {
        try {
          const runtime = await import('@/src/location/presenceRuntime');
          if (!(await runtime.isEnabled())) return;
          await runtime.reconcile();
          await runtime.syncRegions();
        } catch {
          /* offline, or no permission: both are ordinary and neither is fatal */
        }
      })();
    };

    catchUp();
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active') catchUp();
    });
    return () => sub.remove();
  }, []);
}

function ThemedStack() {
  const { colors } = useTheme();
  const transitionMs = useShellTransitionMs();
  usePresenceReconciliation();
  return (
    <View style={{ flex: 1, backgroundColor: colors.backgroundPrimary }}>
      {/*
        One place decides whether anyone is signed in. Screens below can then
        assume there is a session and spend their loading state on their own
        data instead of on an auth question they were never asked to answer.
      */}
      <AuthGate>
        <Stack
          screenOptions={{
            headerShown: false,
            contentStyle: { backgroundColor: colors.backgroundPrimary },
            // Ambient ↔ Focus foundation (~220–280ms); 0 when reduce-motion
            animation: transitionMs === 0 ? 'none' : 'fade',
            animationDuration: transitionMs || undefined,
            // iOS: keep the native edge swipe. Nothing in the product holds
            // unsaved input that a back gesture could silently discard.
            gestureEnabled: true,
            fullScreenGestureEnabled: true,
          }}
        />
      </AuthGate>
    </View>
  );
}

export default function RootLayout() {
  const [loaded, error] = useIconFonts();

  // Document language and the product's focus ring — see webGlobals.
  useEffect(() => {
    installWebGlobals();
  }, []);

  useEffect(() => {
    if (loaded || error) {
      SplashScreen.hideAsync();
    }
  }, [loaded, error]);

  if (!loaded && !error) return null;

  return (
    <GestureHandlerRootView style={{ flex: 1, backgroundColor: tokens.color.backgroundPrimary }}>
      <SafeAreaProvider>
        <ThemeProvider>
          <ShellModeProvider>
            <AuthProvider>
              <ThemedStack />
            </AuthProvider>
          </ShellModeProvider>
        </ThemeProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
