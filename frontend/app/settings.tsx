/**
 * Connessioni e servizi — what is attached to ORA, and what each one does.
 *
 * This route used to be the whole of "Impostazioni": a photo, the access
 * methods, the location preference, the calendar connectors and the model
 * provider diagnostics, stacked in one scroll. Six unrelated jobs on one page
 * meant nothing on it had a hierarchy, and the two Google entries sat close
 * enough together to suggest that signing in with Google was what let ORA read
 * a Google calendar. Identity moved to Profilo, access methods and location to
 * Permessi; what is left here is the one question the page is now named after.
 *
 * The route name is unchanged on purpose — Home's calendar prompts and the
 * Apple Calendar flow all land here, and they all mean "the place where you
 * connect a calendar". None of the connector logic below is new: the handlers,
 * the OAuth start, the sync, the revoke and the confirmations are the ones
 * that already worked.
 */
import { useCallback, useEffect, useState, type ComponentProps, type ReactNode } from 'react';
import { Platform, StyleSheet, Text, View } from 'react-native';
import { Stack, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

import { tokens } from '@/src/theme/tokens';
import { useTheme } from '@/src/theme/ThemeProvider';
import {
  api,
  AppleCalendarConfigStatus,
  ConnectorInstance,
  LLMProvidersStatus,
} from '@/src/api/client';
import { humanizeError } from '@/src/utils/errors';
import { haptic } from '@/src/utils/haptic';
import { useInflight } from '@/src/shell';
import { ActionBtn } from '@/src/components/ui/ActionBtn';
import { ConfirmDialog } from '@/src/components/ui/ConfirmDialog';
import { DevDiagnostics } from '@/src/components/dev/DevDiagnostics';
import {
  BoundaryNote,
  CALENDAR_WRITE_BOUNDARY,
  InlineError,
  SettingCard,
  StatusPill,
  SubpageShell,
  connectionStateOf,
  lastSyncLabel,
  type ConnectionState,
} from '@/src/components/account';

export default function ConnessioniScreen() {
  const router = useRouter();
  const { colors } = useTheme();

  const [instance, setInstance] = useState<ConnectorInstance | null>(null);
  const [appleConfig, setAppleConfig] = useState<AppleCalendarConfigStatus | null>(null);
  const [appleInstance, setAppleInstance] = useState<ConnectorInstance | null>(null);
  const [llmStatus, setLlmStatus] = useState<LLMProvidersStatus | null>(null);
  const [gcalWrite, setGcalWrite] = useState<{
    connected: boolean;
    needs_reconnect?: boolean;
    account_email?: string | null;
    write_capable?: boolean;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmRevoke, setConfirmRevoke] = useState(false);
  const [confirmAppleRevoke, setConfirmAppleRevoke] = useState(false);

  /**
   * Each read stands on its own.
   *
   * A Google status that times out must not take Apple Calendar off the page
   * with it — the old `Promise.all` made every connector depend on every other
   * one being reachable.
   */
  const load = useCallback(async () => {
    setError(null);
    const attempt = async <T,>(run: () => Promise<T>): Promise<T | null> => {
      try {
        return await run();
      } catch {
        return null;
      }
    };
    const isIOS = Platform.OS === 'ios';
    const [r, aConfig, aInstances, llm, writeStatus] = await Promise.all([
      attempt(() => api.googleCalendarInstances()),
      isIOS ? attempt(() => api.appleCalendarConfig()) : Promise.resolve(null),
      isIOS ? attempt(() => api.appleCalendarInstances()) : Promise.resolve(null),
      attempt(() => api.llmProviders()),
      attempt(() => api.googleCalendarWriteStatus()),
    ]);
    setInstance((r?.items || [])[0] || null);
    setAppleConfig(aConfig);
    setAppleInstance((aInstances?.items || [])[0] || null);
    setLlmStatus(llm);
    setGcalWrite(writeStatus);
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const startGoogleOAuth = useCallback(async () => {
    haptic('tap');
    try {
      const r = await api.googleCalendarOAuthStart();
      const win: any = typeof window !== 'undefined' ? window : null;
      if (win?.location) win.location.assign(r.authorize_url);
      else router.push('/(tabs)');
    } catch (e: any) {
      setError(humanizeError(e, 'connect'));
    }
  }, [router]);

  const guard = useInflight();

  const onSync = useCallback(() => guard(async () => {
    if (!instance) return;
    haptic('medium');
    setBusy('sync');
    setError(null);
    try {
      await api.googleCalendarSync(instance.id);
      haptic('success');
      await load();
    } catch (e: any) {
      haptic('error');
      setError(humanizeError(e, 'sync'));
    } finally {
      setBusy(null);
    }
  }), [guard, instance, load]);

  const onRevoke = useCallback(async () => {
    if (!instance) return;
    haptic('warning');
    setBusy('revoke');
    setError(null);
    try {
      await api.googleCalendarRevoke(instance.id);
      haptic('success');
      setConfirmRevoke(false);
      await load();
    } catch (e: any) {
      haptic('error');
      setError(humanizeError(e, 'revoke'));
    } finally {
      setBusy(null);
    }
  }, [instance, load]);

  const onAppleDisconnect = useCallback(async () => {
    if (!appleInstance) return;
    haptic('warning');
    setBusy('apple_revoke');
    setError(null);
    try {
      await api.appleCalendarDisconnect(appleInstance.id);
      haptic('success');
      setConfirmAppleRevoke(false);
      await load();
    } catch (e: any) {
      haptic('error');
      setError(humanizeError(e, 'revoke'));
    } finally {
      setBusy(null);
    }
  }, [appleInstance, load]);

  const googleState = connectionStateOf(instance);
  const appleVisible = Platform.OS === 'ios' && !!appleConfig?.enabled;
  const appleState = connectionStateOf(appleInstance);

  return (
    <>
      <Stack.Screen options={{ headerShown: false }} />
      <SubpageShell
        title="Connessioni e servizi"
        subtitle="I servizi che hai collegato a ORA, e cosa può leggere di ciascuno."
        testID="settings"
      >
        {loading ? (
          /*
            The shape of a service card, not a spinner in an empty page. What
            arrives lands in the same place, so the page does not jump when the
            connectors answer.
          */
          <View testID="connections-skeleton" style={styles.skeleton}>
            <View style={[styles.skBox, { backgroundColor: colors.surface, borderColor: colors.border }]} />
            <View style={[styles.skBox, { backgroundColor: colors.surface, borderColor: colors.border, minHeight: 120 }]} />
          </View>
        ) : (
          <>
            <ServiceCard
              icon="calendar-outline"
              name="Google Calendar"
              state={googleState}
              account={gcalWrite?.account_email || instance?.display_label || null}
              lastSyncAt={instance?.last_sync_at || null}
              purpose="ORA legge i tuoi eventi per capire come è fatta la tua giornata."
              testID="settings-connection"
            >
              {googleState === 'connected' ? (
                <>
                  <View style={styles.actions}>
                    <ActionBtn
                      primary
                      icon="sync"
                      label={busy === 'sync' ? 'Sincronizzo…' : 'Sincronizza'}
                      onPress={onSync}
                      loading={busy === 'sync'}
                      testID="btn-settings-sync"
                    />
                    <ActionBtn
                      variant="ghost"
                      icon="options-outline"
                      label="Scegli i calendari"
                      onPress={() => {
                        haptic('tap');
                        router.push(`/manage-calendars?instance=${instance!.id}`);
                      }}
                      testID="btn-settings-manage"
                    />
                    <ActionBtn
                      variant="danger"
                      icon="unlink-outline"
                      label="Scollega"
                      onPress={() => {
                        haptic('warning');
                        setConfirmRevoke(true);
                      }}
                      disabled={busy === 'revoke'}
                      testID="btn-revoke"
                    />
                  </View>
                  {/*
                    Writing back to Google needs a scope the first connection
                    may not have asked for. It is stated as a thing ORA cannot
                    do yet rather than as an error the person caused.
                  */}
                  {gcalWrite?.needs_reconnect ? (
                    <View style={styles.reconnect}>
                      <Text style={[styles.reconnectText, { color: colors.textSecondary }]}>
                        Per ora ORA può leggere questo calendario ma non scriverci. Serve una nuova
                        autorizzazione da Google.
                      </Text>
                      <View style={styles.actions}>
                        <ActionBtn
                          primary
                          icon="logo-google"
                          label="Autorizza la scrittura"
                          onPress={() => void startGoogleOAuth()}
                        />
                      </View>
                    </View>
                  ) : null}
                  <BoundaryNote>{CALENDAR_WRITE_BOUNDARY}</BoundaryNote>
                </>
              ) : (
                <View style={styles.actions}>
                  <ActionBtn
                    primary
                    icon="logo-google"
                    label={googleState === 'disconnected' ? 'Ricollega' : 'Collega Google Calendar'}
                    onPress={() => void startGoogleOAuth()}
                  />
                </View>
              )}
            </ServiceCard>

            {appleVisible ? (
              <ServiceCard
                icon="logo-apple"
                name="Apple Calendar"
                state={appleState}
                account={appleInstance?.display_label || null}
                lastSyncAt={appleInstance?.last_sync_at || null}
                purpose="Gli eventi del calendario del tuo iPhone."
                testID={appleState === 'connected' ? 'apple-cal-connected' : 'apple-cal-empty'}
              >
                <View style={styles.actions}>
                  <ActionBtn
                    primary={appleState !== 'connected'}
                    icon={appleState === 'connected' ? 'sync' : 'link-outline'}
                    label={appleState === 'connected' ? 'Sincronizza' : 'Collega Apple Calendar'}
                    onPress={() => {
                      haptic('tap');
                      router.push('/connect-apple-calendar');
                    }}
                    testID="btn-connect-apple"
                  />
                  {appleState === 'connected' ? (
                    <ActionBtn
                      variant="danger"
                      icon="unlink-outline"
                      label="Scollega"
                      onPress={() => {
                        haptic('warning');
                        setConfirmAppleRevoke(true);
                      }}
                      disabled={busy === 'apple_revoke'}
                      testID="btn-apple-revoke"
                    />
                  ) : null}
                </View>
              </ServiceCard>
            ) : null}

            {error ? <InlineError>{error}</InlineError> : null}

            <DevDiagnostics
              llmStatus={llmStatus}
              busy={busy}
              onSelectProvider={async (id) => {
                haptic('tap');
                setBusy(`llm_${id}`);
                setError(null);
                try {
                  const res = await api.setLlmProvider(id);
                  setLlmStatus((prev) =>
                    prev
                      ? {
                          ...prev,
                          active: res.active,
                          user_preference: res.user_preference,
                          providers: res.providers,
                          fallback_chain: res.fallback_chain,
                          preferred: res.user_preference === 'auto' ? null : res.user_preference,
                        }
                      : prev,
                  );
                  haptic('success');
                } catch (e: any) {
                  haptic('error');
                  setError(humanizeError(e));
                } finally {
                  setBusy(null);
                }
              }}
            />
          </>
        )}
      </SubpageShell>

      <ConfirmDialog
        open={confirmRevoke}
        testID="confirm-revoke"
        title="Vuoi scollegare Google Calendar?"
        body="ORA smetterà di vedere i tuoi eventi. Puoi ricollegarlo quando vuoi."
        confirmLabel="Scollega"
        destructive
        busy={busy === 'revoke'}
        onCancel={() => setConfirmRevoke(false)}
        onConfirm={onRevoke}
        confirmTestID="btn-confirm-revoke"
      />
      <ConfirmDialog
        open={confirmAppleRevoke}
        testID="confirm-apple-revoke"
        title="Vuoi scollegare Apple Calendar?"
        body="ORA smetterà di ricevere gli eventi dall’iPhone. Puoi ricollegarlo quando vuoi."
        confirmLabel="Scollega"
        destructive
        busy={busy === 'apple_revoke'}
        onCancel={() => setConfirmAppleRevoke(false)}
        onConfirm={onAppleDisconnect}
        confirmTestID="btn-confirm-apple-revoke"
      />
    </>
  );
}

/**
 * One connected service.
 *
 * Name, whether it is connected, which account it is, when it last read
 * anything, and what ORA does with it. No provider id, no scope list, no token
 * state — those describe the integration, and a person here is asking about
 * their calendar.
 */
function ServiceCard({
  icon,
  name,
  state,
  account,
  lastSyncAt,
  purpose,
  children,
  testID,
}: {
  icon: ComponentProps<typeof Ionicons>['name'];
  name: string;
  state: ConnectionState;
  account?: string | null;
  lastSyncAt?: string | null;
  purpose: string;
  children?: ReactNode;
  testID?: string;
}) {
  const { colors } = useTheme();
  return (
    <SettingCard testID={testID}>
      <View style={styles.serviceHead}>
        <View style={[styles.serviceIcon, { backgroundColor: colors.accentMuted }]}>
          <Ionicons name={icon} size={19} color={colors.accent} />
        </View>
        <View style={styles.serviceText}>
          <Text
            style={[styles.serviceName, { color: colors.textPrimary }]}
            accessibilityRole="header"
            aria-level={2}
          >
            {name}
          </Text>
          {account ? (
            <Text style={[styles.serviceMeta, { color: colors.textSecondary }]} numberOfLines={1}>
              {account}
            </Text>
          ) : null}
        </View>
        <StatusPill state={state} />
      </View>

      <Text style={[styles.servicePurpose, { color: colors.textSecondary }]}>{purpose}</Text>
      {state === 'connected' ? (
        <Text style={[styles.serviceMeta, { color: colors.textTertiary }]}>
          {lastSyncLabel(lastSyncAt)}
        </Text>
      ) : null}

      {children}
    </SettingCard>
  );
}

const styles = StyleSheet.create({
  skeleton: { gap: tokens.spacing.lg },
  skBox: {
    minHeight: 200, borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
  },
  serviceHead: { flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.md },
  serviceIcon: {
    width: 40, height: 40, borderRadius: tokens.radius.sm,
    alignItems: 'center', justifyContent: 'center',
  },
  serviceText: { flex: 1, minWidth: 0, gap: 2 },
  serviceName: { fontSize: 16, fontWeight: '650' as any, letterSpacing: -0.2 },
  serviceMeta: { fontSize: 12, lineHeight: 17 },
  servicePurpose: { fontSize: 13, lineHeight: 19, marginTop: 2 },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: tokens.spacing.sm, marginTop: tokens.spacing.sm },
  reconnect: { gap: tokens.spacing.sm, marginTop: tokens.spacing.sm },
  reconnectText: { fontSize: 13, lineHeight: 19 },
});
