/**
 * Google Sign-In → returns ID token for backend verification.
 * Uses expo-auth-session; does not keep Google tokens as app session.
 *
 * Web redirect URI = current origin (`window.location.origin`). Google Cloud
 * Console must list BOTH http://localhost:8081 and http://127.0.0.1:8081 as
 * Authorized JavaScript origins AND Authorized redirect URIs — they are
 * different origins to Google.
 */
import { Platform } from 'react-native';
import * as Google from 'expo-auth-session/providers/google';
import * as WebBrowser from 'expo-web-browser';
import { makeRedirectUri } from 'expo-auth-session';
import { googleClientIds, googleConfiguredForPlatform, notConfiguredMessage } from './providersConfig';

WebBrowser.maybeCompleteAuthSession();

export type GoogleSignInResult =
  | { ok: true; idToken: string; nonce?: string }
  | { ok: false; cancelled?: boolean; error: string };

/** Explicit web redirect from the live browser origin (localhost vs 127.0.0.1). */
function webRedirectUri(): string | undefined {
  if (Platform.OS !== 'web') return undefined;
  if (typeof window !== 'undefined' && window.location?.origin) {
    return window.location.origin;
  }
  return makeRedirectUri();
}

export function useGoogleAuthRequest() {
  const ids = googleClientIds();
  const redirectUri = webRedirectUri();
  return Google.useIdTokenAuthRequest({
    clientId: ids.web || undefined,
    iosClientId: ids.ios || undefined,
    androidClientId: ids.android || undefined,
    webClientId: ids.web || undefined,
    ...(redirectUri ? { redirectUri } : {}),
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
