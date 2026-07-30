import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';
import { LogBox, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { StatusBar } from 'expo-status-bar';

import { useIconFonts } from '@/src/hooks/use-icon-fonts';
import { AuthProvider } from '@/src/contexts/AuthContext';
import { tokens } from '@/src/theme/tokens';

LogBox.ignoreAllLogs(true);
SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const [loaded, error] = useIconFonts();

  useEffect(() => {
    if (loaded || error) {
      SplashScreen.hideAsync();
    }
  }, [loaded, error]);

  if (!loaded && !error) return null;

  return (
    <GestureHandlerRootView style={{ flex: 1, backgroundColor: tokens.color.surface }}>
      <SafeAreaProvider>
        <AuthProvider>
          <StatusBar style="light" />
          <View style={{ flex: 1, backgroundColor: tokens.color.surface }}>
            <Stack
              screenOptions={{
                headerShown: false,
                contentStyle: { backgroundColor: tokens.color.surface },
                animation: 'fade',
              }}
            />
          </View>
        </AuthProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
