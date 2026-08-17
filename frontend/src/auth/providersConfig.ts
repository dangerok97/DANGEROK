/**
 * Public social-auth configuration (Expo EXPO_PUBLIC_* only).
 */
import { Platform } from 'react-native';

import { getGoogleAuthAvailability, googleClientIds } from './googleAuthAvailability';

export type SocialProviderStatus = {
  google: { configured: boolean; platforms: Record<string, boolean> };
  apple: { configured: boolean; platforms: Record<string, boolean>; web_secret_ready?: boolean };
  password: { configured: boolean };
};

const NOT_CONFIGURED = 'Integrazione non configurata in questo ambiente';

export function appleServiceId() {
  return (process.env.EXPO_PUBLIC_APPLE_SERVICE_ID || '').trim();
}

export function googleConfiguredForPlatform(): boolean {
  return getGoogleAuthAvailability(Platform.OS, googleClientIds()).status === 'ready';
}

/** Apple native button only on iOS; web/Android need Services ID. */
export function appleConfiguredForPlatform(): boolean {
  if (Platform.OS === 'ios') return true; // capability checked at runtime
  return Boolean(appleServiceId());
}

export function notConfiguredMessage() {
  return NOT_CONFIGURED;
}
