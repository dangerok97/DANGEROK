import { Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';
import { createTokenStore } from './tokenStore';
import { PENDING_SESSION_CLEANUP_KEY } from './sessionCleanup';

const TOKEN_KEY = 'ora_auth_token';
const SIGNED_OUT_KEY = 'ora_auth_signed_out_v1';
const native = Platform.OS === 'ios' || Platform.OS === 'android';

export const authToken = createTokenStore({
  readToken: async () => {
    // Same key and JSON format as the existing secure storage wrapper, but
    // unavailable storage now throws instead of pretending no session exists.
    const raw = native ? await SecureStore.getItemAsync(TOKEN_KEY) : await AsyncStorage.getItem(TOKEN_KEY);
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    return typeof value === 'string' && value ? value : null;
  },
  writeToken: async token => {
    if (native) await SecureStore.setItemAsync(TOKEN_KEY, JSON.stringify(token));
    else await AsyncStorage.setItem(TOKEN_KEY, JSON.stringify(token));
  },
  removeToken: async () => {
    if (native) await SecureStore.deleteItemAsync(TOKEN_KEY);
    else await AsyncStorage.removeItem(TOKEN_KEY);
  },
  // This marker contains no credential or account identifier. It remains
  // readable if the OS keychain is temporarily locked during an exit.
  readSignedOut: async () => await AsyncStorage.getItem(SIGNED_OUT_KEY) === '1',
  writeSignedOut: value => AsyncStorage.setItem(SIGNED_OUT_KEY, value ? '1' : '0'),
  isRevocationPending: async token => {
    const raw = native
      ? await SecureStore.getItemAsync(PENDING_SESSION_CLEANUP_KEY)
      : await AsyncStorage.getItem(PENDING_SESSION_CLEANUP_KEY);
    if (!raw) return false;
    // Native stores the protected array directly; the web storage wrapper
    // JSON-encodes its string value. Neither path turns it into login state.
    let rows: unknown = JSON.parse(raw);
    if (typeof rows === 'string') rows = JSON.parse(rows);
    if (!Array.isArray(rows)) throw new Error('invalid_session_cleanup');
    return rows.some(row => row && row.token === token);
  },
});
