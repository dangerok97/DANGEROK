import type { GoogleAuthAvailability, GoogleAuthFailure } from './googleAuth.types';

export type GoogleClientIds = {
  web: string;
  ios: string;
  android: string;
};

export const GOOGLE_UNAVAILABLE_MESSAGE =
  'Accesso con Google non disponibile in questo momento.';
export const GOOGLE_CANCELLED_MESSAGE = 'Accesso Google annullato.';
export const GOOGLE_NETWORK_MESSAGE = 'Non riesco a collegarmi a Google. Riprova tra poco.';

export function googleClientIds(): GoogleClientIds {
  return {
    web: (process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID || '').trim(),
    ios: (process.env.EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID || '').trim(),
    android: (process.env.EXPO_PUBLIC_GOOGLE_ANDROID_CLIENT_ID || '').trim(),
  };
}
export function getGoogleAuthAvailability(
  platform: string,
  ids: GoogleClientIds = googleClientIds(),
): GoogleAuthAvailability {
  if (platform === 'web') {
    return ids.web
      ? { status: 'ready' }
      : { status: 'missing_frontend_config', safeMessage: GOOGLE_UNAVAILABLE_MESSAGE };
  }
  if (platform === 'ios') {
    return ids.web && ids.ios
      ? { status: 'ready' }
      : { status: 'missing_frontend_config', safeMessage: GOOGLE_UNAVAILABLE_MESSAGE };
  }
  if (platform === 'android') {
    return ids.web && ids.android
      ? { status: 'ready' }
      : { status: 'missing_frontend_config', safeMessage: GOOGLE_UNAVAILABLE_MESSAGE };
  }
  return { status: 'unsupported', safeMessage: GOOGLE_UNAVAILABLE_MESSAGE };
}

export function googleAuthFailure(
  raw: unknown,
  fallbackCode = 'provider_error',
): GoogleAuthFailure {
  const value = raw as { code?: unknown; message?: unknown } | null;
  const code = String(value?.code || fallbackCode).toLowerCase();
  const message = String(value?.message || raw || '').toLowerCase();
  const cancelled =
    code.includes('cancel') ||
    code.includes('dismiss') ||
    message.includes('cancel') ||
    message.includes('dismiss');
  if (cancelled) {
    return { ok: false, code: 'cancelled', safeMessage: GOOGLE_CANCELLED_MESSAGE, cancelled: true };
  }
  if (
    code.includes('network') ||
    message.includes('network') ||
    message.includes('failed to fetch') ||
    message.includes('load failed')
  ) {
    return { ok: false, code: 'network_error', safeMessage: GOOGLE_NETWORK_MESSAGE, cancelled: false };
  }
  return { ok: false, code: fallbackCode, safeMessage: GOOGLE_UNAVAILABLE_MESSAGE, cancelled: false };
}
