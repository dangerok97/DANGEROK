import { useCallback, useEffect, useState } from 'react';
import { Platform } from 'react-native';

import { api, type AppleCalendarConfigStatus, type AuthIdentitiesResponse, type ConnectorInstance } from '@/src/api/client';
import { useAuth } from '@/src/contexts/AuthContext';
import { appleConfiguredForPlatform } from '@/src/auth/providersConfig';

import {
  connectionStateOf,
  type AccessMethod,
  type AccountSnapshot,
  type LocationMode,
  type ServiceModel,
} from './accountModel';

/**
 * One load for the whole account surface, and no single point of failure.
 *
 * These come from five different subsystems, and any one of them can be having
 * a bad day. Reading them with `Promise.all` would mean a Google Calendar
 * status timing out takes the person's own name off the screen — so each read
 * resolves to null on its own and the page renders whatever it has, saying so
 * once. Nothing here is a source of truth; it is five reads composed.
 */

export type AccountData = {
  snapshot: AccountSnapshot;
  /** The connector instances themselves, for the flows that act on them. */
  googleCalendar: ConnectorInstance | null;
  appleCalendar: ConnectorInstance | null;
  appleEnabled: boolean;
  identities: AuthIdentitiesResponse | null;
  googleCalendarNeedsReconnect: boolean;
};

const EMPTY: AccountSnapshot = {
  services: [],
  methods: [],
  location: 'off',
  documentAnalysis: null,
  calendarWriteAuthorised: false,
  partial: false,
};

function methodsFrom(idents: AuthIdentitiesResponse | null): AccessMethod[] {
  if (!idents) return [];
  const appleAvailable = Platform.OS === 'ios' || appleConfiguredForPlatform();
  return [
    {
      id: 'password',
      label: 'Email e password',
      linked: idents.methods.password.linked,
      detail: idents.methods.password.email || idents.email,
      // The password identity has neither an unlink route nor a way to be
      // added later: you either signed up with one or you did not.
      canUnlink: false,
      offerable: false,
    },
    {
      id: 'google',
      label: 'Google',
      linked: idents.methods.google.linked,
      detail: idents.methods.google.email,
      canUnlink: !!idents.can_unlink.google,
      offerable: true,
    },
    {
      id: 'apple',
      label: 'Apple',
      linked: idents.methods.apple.linked,
      detail: idents.methods.apple.email,
      canUnlink: !!idents.can_unlink.apple,
      offerable: appleAvailable,
    },
  ];
}

export function useAccount() {
  const { user } = useAuth();
  const [data, setData] = useState<AccountData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) setLoading(true);
    const failures: string[] = [];
    const attempt = async <T,>(key: string, run: () => Promise<T>): Promise<T | null> => {
      try {
        return await run();
      } catch {
        failures.push(key);
        return null;
      }
    };

    const isIOS = Platform.OS === 'ios';
    const [idents, gcal, gwrite, appleCfg, appleInst, loc, docPrefs] = await Promise.all([
      attempt('identities', () => api.authIdentities()),
      attempt('google_calendar', () => api.googleCalendarInstances()),
      attempt('google_calendar_write', () => api.googleCalendarWriteStatus()),
      isIOS ? attempt('apple_config', () => api.appleCalendarConfig()) : Promise.resolve(null),
      isIOS ? attempt('apple_calendar', () => api.appleCalendarInstances()) : Promise.resolve(null),
      attempt('location', () => api.locationGetPreference()),
      attempt('document_preferences', () => api.documentPreferences()),
    ]);

    const googleInstance = (gcal?.items || [])[0] || null;
    const appleInstance = (appleInst?.items || [])[0] || null;
    const appleEnabled = isIOS && !!(appleCfg as AppleCalendarConfigStatus | null)?.enabled;

    const services: ServiceModel[] = [
      {
        id: 'google_calendar',
        name: 'Google Calendar',
        state: connectionStateOf(googleInstance),
        account: gwrite?.account_email || googleInstance?.display_label || null,
        lastSyncAt: googleInstance?.last_sync_at || null,
      },
    ];
    if (appleEnabled) {
      services.push({
        id: 'apple_calendar',
        name: 'Apple Calendar',
        state: connectionStateOf(appleInstance),
        account: appleInstance?.display_label || null,
        lastSyncAt: appleInstance?.last_sync_at || null,
      });
    }

    const location: LocationMode = loc?.mode === 'while_using' ? 'while_using' : 'off';

    setData({
      snapshot: {
        ...EMPTY,
        name: user?.name,
        email: user?.email,
        picture: user?.picture,
        memberSince: user?.member_since,
        services,
        methods: methodsFrom(idents),
        location,
        documentAnalysis:
          typeof docPrefs?.document_ai_analysis === 'boolean' ? docPrefs.document_ai_analysis : null,
        calendarWriteAuthorised: !!gwrite?.write_capable,
        partial: failures.length > 0,
      },
      googleCalendar: googleInstance,
      appleCalendar: appleInstance,
      appleEnabled,
      identities: idents,
      googleCalendarNeedsReconnect: !!gwrite?.needs_reconnect,
    });
    // A failure that took everything with it is worth naming; a partial one is
    // already said quietly in the page itself.
    setError(failures.length >= 5 ? 'Alcune informazioni non sono raggiungibili in questo momento.' : null);
    setLoading(false);
  }, [user?.name, user?.email, user?.picture, user?.member_since]);

  useEffect(() => {
    void load();
  }, [load]);

  return { data, loading, error, reload: load };
}
