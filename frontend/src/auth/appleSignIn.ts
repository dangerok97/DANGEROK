/**
 * Apple Sign-In — native iOS via expo-apple-authentication;
 * web/Android via AuthSession when Services ID is configured.
 */
import { Platform } from 'react-native';
import * as AppleAuthentication from 'expo-apple-authentication';
import * as Crypto from 'expo-crypto';
import * as AuthSession from 'expo-auth-session';
import * as WebBrowser from 'expo-web-browser';
import { appleConfiguredForPlatform, appleServiceId, notConfiguredMessage } from './providersConfig';

WebBrowser.maybeCompleteAuthSession();

export type AppleSignInResult =
  | {
      ok: true;
      idToken: string;
      nonce: string;
      email?: string | null;
      fullName?: { givenName?: string | null; familyName?: string | null } | null;
    }
  | { ok: false; cancelled?: boolean; error: string };

async function makeNonce(): Promise<{ raw: string; hashed: string }> {
  const bytes = await Crypto.getRandomBytesAsync(16);
  const raw = Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
  const hashed = await Crypto.digestStringAsync(
    Crypto.CryptoDigestAlgorithm.SHA256,
    raw,
    { encoding: Crypto.CryptoEncoding.HEX },
  );
  return { raw, hashed };
}

export async function isAppleNativeAvailable(): Promise<boolean> {
  if (Platform.OS !== 'ios') return false;
  try {
    return await AppleAuthentication.isAvailableAsync();
  } catch {
    return false;
  }
}

export async function signInWithAppleNative(): Promise<AppleSignInResult> {
  if (Platform.OS !== 'ios') {
    return { ok: false, error: notConfiguredMessage() };
  }
  const available = await isAppleNativeAvailable();
  if (!available) {
    return { ok: false, error: notConfiguredMessage() };
  }
  try {
    const { raw, hashed } = await makeNonce();
    const cred = await AppleAuthentication.signInAsync({
      requestedScopes: [
        AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
        AppleAuthentication.AppleAuthenticationScope.EMAIL,
      ],
      nonce: hashed,
    });
    if (!cred.identityToken) {
      return { ok: false, error: 'Identity token Apple mancante' };
    }
    return {
      ok: true,
      idToken: cred.identityToken,
      nonce: raw,
      email: cred.email,
      fullName: cred.fullName
        ? { givenName: cred.fullName.givenName, familyName: cred.fullName.familyName }
        : null,
    };
  } catch (e: any) {
    if (e?.code === 'ERR_REQUEST_CANCELED' || e?.code === 'ERR_CANCELED') {
      return { ok: false, cancelled: true, error: 'Accesso Apple annullato' };
    }
    return { ok: false, error: e?.message || 'Errore Sign in with Apple' };
  }
}

/** Browser OAuth for web / Android — requires Services ID + redirect in Apple Developer. */
export async function signInWithAppleWeb(): Promise<AppleSignInResult> {
  const clientId = appleServiceId();
  if (!clientId) {
    return { ok: false, error: notConfiguredMessage() };
  }
  try {
    const { raw, hashed } = await makeNonce();
    const redirectUri =
      (process.env.EXPO_PUBLIC_APPLE_REDIRECT_URI || '').trim() ||
      AuthSession.makeRedirectUri({ scheme: 'frontend', path: 'login' });
    const state = raw.slice(0, 16);
    const authUrl =
      `https://appleid.apple.com/auth/authorize` +
      `?client_id=${encodeURIComponent(clientId)}` +
      `&redirect_uri=${encodeURIComponent(redirectUri)}` +
      `&response_type=code%20id_token` +
      `&response_mode=fragment` +
      `&scope=name%20email` +
      `&nonce=${encodeURIComponent(hashed)}` +
      `&state=${encodeURIComponent(state)}`;

    const res = await WebBrowser.openAuthSessionAsync(authUrl, redirectUri);
    if (res.type !== 'success' || !('url' in res) || !res.url) {
      return { ok: false, cancelled: true, error: 'Accesso Apple annullato' };
    }
    const url = res.url;
    const hash = url.includes('#') ? url.split('#')[1] : url.split('?')[1] || '';
    const params = new URLSearchParams(hash);
    const idToken = params.get('id_token');
    if (!idToken) {
      return { ok: false, error: 'ID token Apple mancante dal callback' };
    }
    return { ok: true, idToken, nonce: raw };
  } catch (e: any) {
    return { ok: false, error: e?.message || 'Errore Apple web login' };
  }
}

export async function signInWithApple(): Promise<AppleSignInResult> {
  if (!appleConfiguredForPlatform() && Platform.OS !== 'ios') {
    return { ok: false, error: notConfiguredMessage() };
  }
  if (Platform.OS === 'ios') {
    return signInWithAppleNative();
  }
  return signInWithAppleWeb();
}
