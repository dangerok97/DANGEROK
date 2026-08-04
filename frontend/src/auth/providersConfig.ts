/**
 * Public social-auth configuration (Expo EXPO_PUBLIC_* only).
 */
import { Platform } from 'react-native';

export type SocialProviderStatus = {
  google: { configured: boolean; platforms: Record<string, boolean> };
  apple: { configured: boolean; platforms: Record<string, boolean>; web_secret_ready?: boolean };
  password: { configured: boolean };
};

const NOT_CONFIGURED = 'Integrazione non configurata in questo ambiente';

export function googleClientIds() {
  return {
    web: (process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID || '').trim(),
    ios: (process.env.EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID || '').trim(),
    android: (process.env.EXPO_PUBLIC_GOOGLE_ANDROID_CLIENT_ID || '').trim(),
  };
}

export function appleServiceId() {
  return (process.env.EXPO_PUBLIC_APPLE_SERVICE_ID || '').trim();
}

export function googleConfiguredForPlatform(): boolean {
  const ids = googleClientIds();
  if (Platform.OS === 'ios') return Boolean(ids.ios || ids.web);
  if (Platform.OS === 'android') return Boolean(ids.android || ids.web);
  return Boolean(ids.web);
}

/** Apple native button only on iOS; web/Android need Services ID. */
export function appleConfiguredForPlatform(): boolean {
  if (Platform.OS === 'ios') return true; // capability checked at runtime
  return Boolean(appleServiceId());
}

export function notConfiguredMessage() {
  return NOT_CONFIGURED;
}
