import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  getGoogleAuthAvailability,
  googleAuthFailure,
  googleClientIds,
  GOOGLE_UNAVAILABLE_MESSAGE,
} from './googleAuthAvailability';
import type {
  GoogleAuthAdapter,
  GoogleAuthResult,
} from './googleAuth.types';

type GisCredentialResponse = { credential?: string; select_by?: string };
type GisApi = {
  accounts: {
    id: {
      initialize: (config: {
        client_id: string;
        callback: (response: GisCredentialResponse) => void;
        ux_mode: 'popup';
        auto_select: boolean;
        cancel_on_tap_outside: boolean;
      }) => void;
      renderButton: (
        container: HTMLElement,
        options: {
          type: 'standard';
          theme: 'outline';
          size: 'large';
          text: 'continue_with';
          shape: 'rectangular';
          logo_alignment: 'left';
          width: number;
          click_listener: () => void;
        },
      ) => void;
    };
  };
};

declare global {
  interface Window {
    google?: GisApi;
  }
}

const GIS_SRC = 'https://accounts.google.com/gsi/client';
const GIS_SCRIPT_ID = 'ora-google-identity-services';
const GIS_LOAD_TIMEOUT_MS = 15_000;
const GIS_READY_POLL_MS = 25;
let gisLoadPromise: Promise<GisApi> | null = null;
let gisInitialized = false;
let gisCredentialHandler: ((response: GisCredentialResponse) => void) | null = null;

function findGoogleIdentityServicesScript(): HTMLScriptElement | null {
  return (
    (document.getElementById(GIS_SCRIPT_ID) as HTMLScriptElement | null) ||
    document.querySelector<HTMLScriptElement>(`script[src="${GIS_SRC}"]`)
  );
}

function removeGoogleIdentityServicesScript(script: HTMLScriptElement): void {
  if (script.parentNode) script.parentNode.removeChild(script);
}

export function loadGoogleIdentityServices(): Promise<GisApi> {
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return Promise.reject(new Error('google_provider_unavailable'));
  }
  if (window.google?.accounts?.id) {
    return Promise.resolve(window.google);
  }
  if (gisLoadPromise) {
    return gisLoadPromise;
  }

  gisLoadPromise = new Promise<GisApi>((resolve, reject) => {
    let script = findGoogleIdentityServicesScript();
    // A completed/failed tag without the GIS global cannot emit load/error again.
    // Replace it now so a retry always has a real network lifecycle.
    if (
      script &&
      (script.dataset.oraGisState === 'loaded' || script.dataset.oraGisState === 'error')
    ) {
      removeGoogleIdentityServicesScript(script);
      script = null;
    }
    const isNewScript = !script;
    script ||= document.createElement('script');
    let settled = false;
    let timeoutId: ReturnType<typeof setTimeout>;
    let pollId: ReturnType<typeof setInterval>;

    const cleanup = () => {
      clearTimeout(timeoutId);
      clearInterval(pollId);
      script.removeEventListener('load', onLoad);
      script.removeEventListener('error', onError);
    };
    const succeedIfReady = (): boolean => {
      if (settled || !window.google?.accounts?.id) return false;
      settled = true;
      script.dataset.oraGisState = 'loaded';
      cleanup();
      resolve(window.google);
      return true;
    };
    const fail = () => {
      if (settled) return;
      settled = true;
      script.dataset.oraGisState = 'error';
      cleanup();
      removeGoogleIdentityServicesScript(script);
      gisLoadPromise = null;
      reject(new Error('google_script_load_failed'));
    };
    const onLoad = () => {
      script.dataset.oraGisState = 'loaded';
      // GIS normally installs the global before load; polling also covers a
      // short publication race without leaving the Promise pending forever.
      succeedIfReady();
    };
    const onError = () => {
      fail();
    };

    script.addEventListener('load', onLoad);
    script.addEventListener('error', onError);
    timeoutId = setTimeout(fail, GIS_LOAD_TIMEOUT_MS);
    pollId = setInterval(succeedIfReady, GIS_READY_POLL_MS);

    // Covers Strict Mode/remount and a pre-existing tag that loaded before
    // this invocation registered its listeners.
    if (succeedIfReady()) return;

    if (isNewScript) {
      script.id = GIS_SCRIPT_ID;
      script.src = GIS_SRC;
      script.async = true;
      script.defer = true;
      script.dataset.oraGisState = 'loading';
      document.head.appendChild(script);
    }
  });
  return gisLoadPromise;
}

export function useGoogleAuth(): GoogleAuthAdapter {
  const ids = useMemo(() => googleClientIds(), []);
  const baseAvailability = useMemo(() => getGoogleAuthAvailability('web', ids), [ids]);
  const [runtimeStatus, setRuntimeStatus] = useState<'idle' | 'loading' | 'error'>('idle');
  const buttonResultHandler = useRef<((result: GoogleAuthResult) => void) | null>(null);
  const buttonTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (buttonTimeout.current) clearTimeout(buttonTimeout.current);
    buttonResultHandler.current = null;
  }, []);

  const renderButton = useCallback(async (
    container: HTMLElement,
    onResult: (result: GoogleAuthResult) => void,
    options?: { width?: number },
  ): Promise<void> => {
    buttonResultHandler.current = onResult;
    if (baseAvailability.status !== 'ready') {
      onResult({
        ok: false,
        code: 'missing_frontend_config',
        safeMessage: GOOGLE_UNAVAILABLE_MESSAGE,
        cancelled: false,
      });
      return;
    }
    if (
      container.dataset.oraGisButton === 'loading' ||
      (container.dataset.oraGisButton === 'ready' && container.childElementCount > 0)
    ) return;

    container.dataset.oraGisButton = 'loading';
    let google: GisApi;
    try {
      google = await loadGoogleIdentityServices();
    } catch (error) {
      delete container.dataset.oraGisButton;
      throw error;
    }
    container.replaceChildren();
    gisCredentialHandler = (response) => {
      if (buttonTimeout.current) clearTimeout(buttonTimeout.current);
      buttonTimeout.current = null;
      setRuntimeStatus('idle');
      const handler = buttonResultHandler.current;
      if (!handler) return;
      if (!response.credential) {
        handler(googleAuthFailure(new Error('google_credential_missing'), 'credential_missing'));
        return;
      }
      handler({ ok: true, idToken: response.credential });
    };
    if (!gisInitialized) {
      google.accounts.id.initialize({
        client_id: ids.web,
        ux_mode: 'popup',
        auto_select: false,
        cancel_on_tap_outside: false,
        callback: (response) => gisCredentialHandler?.(response),
      });
      gisInitialized = true;
    }
    google.accounts.id.renderButton(container, {
      type: 'standard',
      theme: 'outline',
      size: 'large',
      text: 'continue_with',
      shape: 'rectangular',
      logo_alignment: 'left',
      width: Math.max(200, Math.min(400, Math.round(options?.width || 400))),
      click_listener: () => {
        setRuntimeStatus('loading');
        if (buttonTimeout.current) clearTimeout(buttonTimeout.current);
        buttonTimeout.current = setTimeout(() => {
          setRuntimeStatus('idle');
          buttonResultHandler.current?.(
            googleAuthFailure(new Error('google_popup_timeout'), 'popup_failed'),
          );
        }, 60_000);
      },
    });
    container.dataset.oraGisButton = 'ready';
  }, [baseAvailability.status, ids.web]);

  const signIn = useCallback((): Promise<GoogleAuthResult> => Promise.resolve({
    ok: false,
    code: 'official_button_required',
    safeMessage: GOOGLE_UNAVAILABLE_MESSAGE,
    cancelled: false,
  }), []);

  const availability =
    baseAvailability.status !== 'ready'
      ? baseAvailability
      : runtimeStatus === 'loading'
        ? { status: 'loading' as const }
        : runtimeStatus === 'error'
          ? { status: 'error' as const, safeMessage: GOOGLE_UNAVAILABLE_MESSAGE }
          : { status: 'ready' as const };

  return {
    availability,
    signIn,
    renderButton,
  };
}
