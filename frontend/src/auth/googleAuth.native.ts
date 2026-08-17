import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Platform } from 'react-native';
import {
  GoogleSignin,
  isCancelledResponse,
  isSuccessResponse,
} from '@react-native-google-signin/google-signin';

import {
  getGoogleAuthAvailability,
  googleAuthFailure,
  googleClientIds,
  GOOGLE_UNAVAILABLE_MESSAGE,
} from './googleAuthAvailability';
import type { GoogleAuthAdapter, GoogleAuthResult } from './googleAuth.types';

export function useGoogleAuth(): GoogleAuthAdapter {
  const ids = useMemo(() => googleClientIds(), []);
  const baseAvailability = useMemo(
    () => getGoogleAuthAvailability(Platform.OS, ids),
    [ids],
  );
  const [runtimeStatus, setRuntimeStatus] = useState<'idle' | 'loading' | 'error'>('idle');
  const pending = useRef<Promise<GoogleAuthResult> | null>(null);

  useEffect(() => {
    if (baseAvailability.status !== 'ready') return;
    GoogleSignin.configure({
      webClientId: ids.web,
      iosClientId: Platform.OS === 'ios' ? ids.ios : undefined,
      offlineAccess: false,
    });
  }, [baseAvailability.status, ids.ios, ids.web]);

  const signIn = useCallback((): Promise<GoogleAuthResult> => {
    if (pending.current) return pending.current;
    if (baseAvailability.status !== 'ready') {
      return Promise.resolve({
        ok: false,
        code: 'missing_frontend_config',
        safeMessage: GOOGLE_UNAVAILABLE_MESSAGE,
        cancelled: false,
      });
    }
    setRuntimeStatus('loading');
    const operation = (async (): Promise<GoogleAuthResult> => {
      try {
        if (Platform.OS === 'android') {
          const available = await GoogleSignin.hasPlayServices({
            showPlayServicesUpdateDialog: true,
          });
          if (!available) return googleAuthFailure(new Error('play_services_unavailable'));
        }
        const response = await GoogleSignin.signIn();
        if (isCancelledResponse(response)) {
          return { ok: false, code: 'cancelled', safeMessage: 'Accesso Google annullato.', cancelled: true };
        }
        if (!isSuccessResponse(response) || !response.data.idToken) {
          return googleAuthFailure(new Error('google_id_token_missing'), 'credential_missing');
        }
        return { ok: true, idToken: response.data.idToken };
      } catch (error) {
        return googleAuthFailure(error);
      }
    })()
      .then((result) => {
        setRuntimeStatus('idle');
        return result;
      })
      .finally(() => {
        pending.current = null;
      });
    pending.current = operation;
    return operation;
  }, [baseAvailability.status]);

  const availability =
    baseAvailability.status !== 'ready'
      ? baseAvailability
      : runtimeStatus === 'loading'
        ? { status: 'loading' as const }
        : runtimeStatus === 'error'
          ? { status: 'error' as const, safeMessage: GOOGLE_UNAVAILABLE_MESSAGE }
          : { status: 'ready' as const };

  return { availability, signIn };
}
