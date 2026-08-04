/**
 * Google Sign-In → returns ID token for backend verification.
 * Uses expo-auth-session; does not keep Google tokens as app session.
 */
import { Platform } from 'react-native';
import * as Google from 'expo-auth-session/providers/google';
import * as WebBrowser from 'expo-web-browser';
import { googleClientIds, googleConfiguredForPlatform, notConfiguredMessage } from './providersConfig';

WebBrowser.maybeCompleteAuthSession();

export type GoogleSignInResult =
  | { ok: true; idToken: string; nonce?: string }
  | { ok: false; cancelled?: boolean; error: string };

export function useGoogleAuthRequest() {
  const ids = googleClientIds();
  return Google.useIdTokenAuthRequest({
    clientId: ids.web || undefined,
    iosClientId: ids.ios || undefined,
    androidClientId: ids.android || undefined,
    webClientId: ids.web || undefined,
  });
}

export async function promptGoogleSignIn(
  promptAsync: (options?: { showInRecents?: boolean }) => Promise<{ type: string; params?: Record<string, string>; authentication?: { idToken?: string | null } | null }>,
): Promise<GoogleSignInResult> {
  if (!googleConfiguredForPlatform()) {
    return { ok: false, error: notConfiguredMessage() };
  }
  try {
    const res = await promptAsync();
    if (res.type === 'dismiss' || res.type === 'cancel') {
      return { ok: false, cancelled: true, error: 'Accesso Google annullato' };
    }
    if (res.type !== 'success') {
      return { ok: false, error: 'Accesso Google non riuscito' };
    }
    const idToken = res.params?.id_token || res.authentication?.idToken || null;
    if (!idToken) {
      return { ok: false, error: 'ID token Google mancante' };
    }
    return { ok: true, idToken: String(idToken) };
  } catch (e: any) {
    return { ok: false, error: e?.message || 'Errore Google Sign-In' };
  }
}

export function googlePlatformHint(): string {
  if (Platform.OS === 'web') return 'web';
  return Platform.OS;
}
