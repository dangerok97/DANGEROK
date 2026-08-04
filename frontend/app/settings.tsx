import { useCallback, useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator, Platform,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { Stack, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import Animated, { FadeInDown, FadeIn } from 'react-native-reanimated';

import { tokens } from '@/src/theme/tokens';
import { api, ConnectorInstance, AppleCalendarConfigStatus, AuthIdentitiesResponse } from '@/src/api/client';
import { humanizeError } from '@/src/utils/errors';
import { haptic } from '@/src/utils/haptic';
import { ActionBtn } from '@/src/components/ui/ActionBtn';
import { formatRelativeAgo } from '@/src/utils/labels';
import { useGoogleAuthRequest, promptGoogleSignIn } from '@/src/auth/googleSignIn';
import { signInWithApple } from '@/src/auth/appleSignIn';
import { googleConfiguredForPlatform, appleConfiguredForPlatform, notConfiguredMessage } from '@/src/auth/providersConfig';

export default function SettingsScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [instance, setInstance] = useState<ConnectorInstance | null>(null);
  const [appleConfig, setAppleConfig] = useState<AppleCalendarConfigStatus | null>(null);
  const [appleInstance, setAppleInstance] = useState<ConnectorInstance | null>(null);
  const [identities, setIdentities] = useState<AuthIdentitiesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmRevoke, setConfirmRevoke] = useState(false);
  const [confirmAppleRevoke, setConfirmAppleRevoke] = useState(false);
  const [eventsCount, setEventsCount] = useState<number | null>(null);
  const [googleRequest, , googlePrompt] = useGoogleAuthRequest();

  const load = useCallback(async () => {
    setError(null);
    try {
      const [r, daily, aConfig, aInstances, idents] = await Promise.all([
        api.googleCalendarInstances(),
        api.dailyToday().catch(() => null),
        // Only iOS shows Apple settings — but we still fetch config to
        // learn the feature-flag state (nothing shown if disabled).
        Platform.OS === 'ios' ? api.appleCalendarConfig().catch(() => null) : Promise.resolve(null),
        Platform.OS === 'ios' ? api.appleCalendarInstances().catch(() => ({ items: [] as ConnectorInstance[] })) : Promise.resolve({ items: [] as ConnectorInstance[] }),
        api.authIdentities().catch(() => null),
      ]);
      setInstance((r.items || [])[0] || null);
      setEventsCount(daily?.total_events ?? null);
      setAppleConfig(aConfig);
      setAppleInstance((aInstances?.items || [])[0] || null);
      setIdentities(idents);
    } catch (e: any) {
      setError(humanizeError(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const onSync = async () => {
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
  };

  const onRevoke = async () => {
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
  };

  const onAppleDisconnect = async () => {
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
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']} testID="settings">
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Pressable
          onPress={() => { haptic('tap'); router.back(); }}
          style={({ pressed }) => [styles.backBtn, pressed && styles.pressed]}
          accessibilityRole="button" accessibilityLabel="Torna indietro" hitSlop={12}
        >
          <Ionicons name="chevron-back" size={22} color={tokens.color.onSurface} />
        </Pressable>
        <Text style={styles.title}>Impostazioni</Text>
        <View style={{ width: 32 }} />
      </View>

      <ScrollView
        contentContainerStyle={{ padding: 20, paddingBottom: insets.bottom + 24, gap: 16 }}
        showsVerticalScrollIndicator={false}
      >
        <Text style={styles.sectionLabel}>Metodi di accesso</Text>
        {identities ? (
          <View style={styles.card} testID="settings-auth-methods">
            <AuthMethodRow
              label="Email"
              linked={identities.methods.password.linked}
              detail={identities.methods.password.email || identities.email}
            />
            <AuthMethodRow
              label="Google"
              linked={identities.methods.google.linked}
              detail={identities.methods.google.email}
              actionLabel={identities.methods.google.linked ? (identities.can_unlink.google ? 'Scollega' : undefined) : 'Collega'}
              busy={busy === 'link_google' || busy === 'unlink_google'}
              onAction={async () => {
                if (identities.methods.google.linked) {
                  if (!identities.can_unlink.google) {
                    setError('Non puoi scollegare l’unico metodo di accesso.');
                    return;
                  }
                  haptic('warning');
                  setBusy('unlink_google');
                  try {
                    await api.unlinkProvider('google');
                    await load();
                  } catch (e: any) {
                    setError(humanizeError(e));
                  } finally {
                    setBusy(null);
                  }
                  return;
                }
                if (!googleConfiguredForPlatform() || !googleRequest) {
                  setError(notConfiguredMessage());
                  return;
                }
                haptic('tap');
                setBusy('link_google');
                try {
                  const res = await promptGoogleSignIn(googlePrompt);
                  if (!res.ok) {
                    if (!res.cancelled) setError(res.error);
                    return;
                  }
                  await api.linkGoogle(res.idToken, res.nonce);
                  await load();
                } catch (e: any) {
                  setError(humanizeError(e));
                } finally {
                  setBusy(null);
                }
              }}
            />
            <AuthMethodRow
              label="Apple"
              linked={identities.methods.apple.linked}
              detail={identities.methods.apple.email}
              actionLabel={
                identities.methods.apple.linked
                  ? (identities.can_unlink.apple ? 'Scollega' : undefined)
                  : (Platform.OS === 'ios' || appleConfiguredForPlatform() ? 'Collega' : undefined)
              }
              busy={busy === 'link_apple' || busy === 'unlink_apple'}
              onAction={async () => {
                if (identities.methods.apple.linked) {
                  if (!identities.can_unlink.apple) {
                    setError('Non puoi scollegare l’unico metodo di accesso.');
                    return;
                  }
                  haptic('warning');
                  setBusy('unlink_apple');
                  try {
                    await api.unlinkProvider('apple');
                    await load();
                  } catch (e: any) {
                    setError(humanizeError(e));
                  } finally {
                    setBusy(null);
                  }
                  return;
                }
                haptic('tap');
                setBusy('link_apple');
                try {
                  const res = await signInWithApple();
                  if (!res.ok) {
                    if (!res.cancelled) setError(res.error);
                    return;
                  }
                  await api.linkApple({ id_token: res.idToken, nonce: res.nonce });
                  await load();
                } catch (e: any) {
                  setError(humanizeError(e));
                } finally {
                  setBusy(null);
                }
              }}
            />
          </View>
        ) : null}

        <Text style={styles.sectionLabel}>Calendari collegati</Text>

        {loading ? (
          <View style={{ padding: 24, alignItems: 'center' }}>
            <ActivityIndicator color={tokens.color.onSurfaceMuted} />
          </View>
        ) : instance ? (
          <Animated.View entering={FadeInDown.duration(220)} style={styles.card} testID="settings-connection">
            <View style={styles.cardHead}>
              <View style={styles.iconWrap}>
                <Ionicons name="calendar-outline" size={18} color={tokens.color.brand} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.cardTitle}>Google Calendar</Text>
                {instance.display_label ? (
                  <Text style={styles.cardMeta}>{instance.display_label}</Text>
                ) : null}
              </View>
              <View style={styles.statusPill}>
                <View style={styles.statusDot} />
                <Text style={styles.statusText}>
                  {instance.status === 'connected' ? 'Collegato' :
                   instance.status === 'revoked' ? 'Scollegato' :
                   instance.status || 'Sconosciuto'}
                </Text>
              </View>
            </View>

            <View style={styles.metaGrid}>
              <MetaItem
                label="Ultima sincronizzazione"
                value={instance.last_sync_at ? formatRelativeAgo(new Date(instance.last_sync_at)) : 'Mai'}
              />
              <MetaItem
                label="Calendari"
                value={String(instance.selected_resource_ids?.length || 0)}
              />
              {typeof eventsCount === 'number' ? (
                <MetaItem label="Eventi oggi" value={String(eventsCount)} />
              ) : null}
            </View>

            {error ? (
              <Animated.View entering={FadeIn.duration(180)} style={styles.errorBanner}>
                <Ionicons name="alert-circle" size={16} color={tokens.color.error} />
                <Text style={styles.errorText}>{error}</Text>
              </Animated.View>
            ) : null}

            <View style={styles.actionsRow}>
              {instance.status !== 'revoked' && (
                <>
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
                    label="Gestisci calendari"
                    onPress={() => { haptic('tap'); router.push(`/manage-calendars?instance=${instance.id}`); }}
                    testID="btn-settings-manage"
                  />
                </>
              )}
              {instance.status !== 'revoked' && (
                <ActionBtn
                  variant="danger"
                  icon="unlink-outline"
                  label="Disconnetti"
                  onPress={() => { haptic('warning'); setConfirmRevoke(true); }}
                  disabled={busy === 'revoke'}
                  testID="btn-revoke"
                />
              )}
              {instance.status === 'revoked' && (
                <ActionBtn
                  primary
                  icon="logo-google"
                  label="Ricollega"
                  onPress={async () => {
                    haptic('tap');
                    try {
                      const r = await api.googleCalendarOAuthStart();
                      const win: any = typeof window !== 'undefined' ? window : null;
                      if (win?.location) win.location.assign(r.authorize_url);
                    } catch (e: any) {
                      setError(humanizeError(e, 'connect'));
                    }
                  }}
                />
              )}
            </View>
          </Animated.View>
        ) : (
          <Animated.View entering={FadeInDown.duration(220)} style={styles.card}>
            <Text style={styles.cardTitle}>Nessun account collegato</Text>
            <Text style={styles.cardMeta}>Torna alla Home per collegare Google Calendar.</Text>
            <View style={styles.actionsRow}>
              <ActionBtn
                icon="home-outline"
                label="Vai alla Home"
                onPress={() => { haptic('tap'); router.push('/(tabs)'); }}
              />
            </View>
          </Animated.View>
        )}

        {/* Apple Calendar row — iOS only, feature-flag gated */}
        {Platform.OS === 'ios' && appleConfig?.enabled ? (
          <AppleCalendarSection
            instance={appleInstance}
            onConnect={() => { haptic('tap'); router.push('/connect-apple-calendar'); }}
            onDisconnect={() => { haptic('warning'); setConfirmAppleRevoke(true); }}
            busy={busy}
          />
        ) : null}
      </ScrollView>

      {/* Confirm revoke */}
      {confirmRevoke ? (
        <View style={styles.overlay}>
          <Animated.View entering={FadeInDown.duration(220)} style={styles.confirmCard} testID="confirm-revoke">
            <Text style={styles.confirmTitle}>Vuoi davvero disconnettere Google Calendar?</Text>
            <Text style={styles.confirmBody}>
              ORA smetterà di ricevere i tuoi eventi. Potrai ricollegarlo quando vuoi.
            </Text>
            <View style={{ flexDirection: 'row', gap: 8, marginTop: 12 }}>
              <ActionBtn label="Annulla" icon="close" onPress={() => setConfirmRevoke(false)} disabled={busy === 'revoke'} />
              <ActionBtn
                variant="danger"
                icon="unlink"
                label="Disconnetti"
                onPress={onRevoke}
                loading={busy === 'revoke'}
                testID="btn-confirm-revoke"
              />
            </View>
          </Animated.View>
        </View>
      ) : null}
      {/* Confirm revoke Apple */}
      {confirmAppleRevoke ? (
        <View style={styles.overlay}>
          <Animated.View entering={FadeInDown.duration(220)} style={styles.confirmCard} testID="confirm-apple-revoke">
            <Text style={styles.confirmTitle}>Vuoi davvero disconnettere Apple Calendar?</Text>
            <Text style={styles.confirmBody}>
              ORA smetterà di ricevere eventi dall{'\''}iPhone. Potrai ricollegarlo quando vuoi.
            </Text>
            <View style={{ flexDirection: 'row', gap: 8, marginTop: 12 }}>
              <ActionBtn label="Annulla" icon="close" onPress={() => setConfirmAppleRevoke(false)} disabled={busy === 'apple_revoke'} />
              <ActionBtn
                variant="danger"
                icon="unlink"
                label="Disconnetti"
                onPress={onAppleDisconnect}
                loading={busy === 'apple_revoke'}
                testID="btn-confirm-apple-revoke"
              />
            </View>
          </Animated.View>
        </View>
      ) : null}
    </SafeAreaView>
  );
}

function AppleCalendarSection({
  instance, onConnect, onDisconnect, busy,
}: {
  instance: ConnectorInstance | null;
  onConnect: () => void;
  onDisconnect: () => void;
  busy: string | null;
}) {
  if (!instance || instance.status === 'revoked') {
    return (
      <Animated.View entering={FadeInDown.duration(220)} style={styles.card} testID="apple-cal-empty">
        <View style={styles.cardHead}>
          <View style={styles.iconWrap}>
            <Ionicons name="logo-apple" size={18} color={tokens.color.onSurface} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.cardTitle}>Apple Calendar</Text>
            <Text style={styles.cardMeta}>Collega il calendario del tuo iPhone/iPad tramite EventKit.</Text>
          </View>
        </View>
        <View style={styles.actionsRow}>
          <ActionBtn
            primary
            icon="link-outline"
            label={instance?.status === 'revoked' ? 'Ricollega' : 'Collega Apple Calendar'}
            onPress={onConnect}
            testID="btn-connect-apple"
          />
        </View>
      </Animated.View>
    );
  }
  return (
    <Animated.View entering={FadeInDown.duration(220)} style={styles.card} testID="apple-cal-connected">
      <View style={styles.cardHead}>
        <View style={styles.iconWrap}>
          <Ionicons name="logo-apple" size={18} color={tokens.color.onSurface} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.cardTitle}>Apple Calendar</Text>
          {instance.display_label ? (
            <Text style={styles.cardMeta}>{instance.display_label}</Text>
          ) : null}
        </View>
        <View style={styles.statusPill}>
          <View style={styles.statusDot} />
          <Text style={styles.statusText}>Collegato</Text>
        </View>
      </View>
      <View style={styles.metaGrid}>
        <MetaItem
          label="Ultima sincronizzazione"
          value={instance.last_sync_at ? formatRelativeAgo(new Date(instance.last_sync_at)) : 'Mai'}
        />
        <MetaItem label="Calendari" value={String(instance.selected_resource_ids?.length || 0)} />
      </View>
      <View style={styles.actionsRow}>
        <ActionBtn
          icon="sync"
          label="Sincronizza di nuovo"
          onPress={onConnect}
        />
        <ActionBtn
          variant="danger"
          icon="unlink-outline"
          label="Disconnetti"
          onPress={onDisconnect}
          disabled={busy === 'apple_revoke'}
          testID="btn-apple-revoke"
        />
      </View>
    </Animated.View>
  );
}

function AuthMethodRow({
  label, linked, detail, actionLabel, onAction, busy,
}: {
  label: string;
  linked: boolean;
  detail?: string | null;
  actionLabel?: string;
  onAction?: () => void;
  busy?: boolean;
}) {
  return (
    <View style={styles.authRow} testID={`auth-method-${label.toLowerCase()}`}>
      <View style={{ flex: 1 }}>
        <Text style={styles.cardTitle}>{label}</Text>
        <Text style={styles.cardMeta}>
          {linked ? (detail || 'Collegato') : 'Non collegato'}
        </Text>
      </View>
      <View style={styles.statusPill}>
        <View style={[styles.statusDot, !linked && { backgroundColor: tokens.color.onSurfaceMuted }]} />
        <Text style={styles.statusText}>{linked ? 'Collegato' : 'Assente'}</Text>
      </View>
      {actionLabel && onAction ? (
        <Pressable
          onPress={onAction}
          disabled={busy}
          style={({ pressed }) => [{ marginLeft: 8, paddingVertical: 6, paddingHorizontal: 8 }, pressed && styles.pressed]}
        >
          {busy ? (
            <ActivityIndicator color={tokens.color.onSurfaceMuted} />
          ) : (
            <Text style={{ color: tokens.color.brand, fontWeight: '600', fontSize: 13 }}>{actionLabel}</Text>
          )}
        </Pressable>
      ) : null}
    </View>
  );
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metaBox} accessible accessibilityLabel={`${label}: ${value}`}>
      <Text style={styles.metaLabel}>{label}</Text>
      <Text style={styles.metaValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: tokens.color.surface },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 12, paddingVertical: 12,
  },
  backBtn: {
    width: 32, height: 32, borderRadius: 16,
    alignItems: 'center', justifyContent: 'center',
  },
  title: { fontSize: 17, fontWeight: '700', color: tokens.color.onSurface },
  sectionLabel: {
    fontSize: 11, color: tokens.color.onSurfaceMuted,
    textTransform: 'uppercase', letterSpacing: 0.5, fontWeight: '600',
  },
  card: {
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: tokens.radius.lg,
    padding: tokens.spacing.lg,
    gap: 12,
    borderWidth: 1, borderColor: tokens.color.border,
  },
  authRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: tokens.color.border,
  },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  iconWrap: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: tokens.color.surfaceTertiary,
    alignItems: 'center', justifyContent: 'center',
  },
  cardTitle: { fontSize: 16, fontWeight: '700', color: tokens.color.onSurface },
  cardMeta: { fontSize: 12, color: tokens.color.onSurfaceMuted, marginTop: 2 },
  statusPill: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: 10, paddingVertical: 4,
    borderRadius: tokens.radius.pill,
    backgroundColor: tokens.color.successBg,
  },
  statusDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: tokens.color.success },
  statusText: { fontSize: 11, color: tokens.color.success, fontWeight: '600' },
  metaGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  metaBox: {
    minWidth: 130, flexGrow: 1, flexBasis: 130,
    backgroundColor: tokens.color.surfaceTertiary,
    padding: 10, borderRadius: tokens.radius.md,
  },
  metaLabel: { fontSize: 10, color: tokens.color.onSurfaceMuted, textTransform: 'uppercase', letterSpacing: 0.5 },
  metaValue: { fontSize: 14, color: tokens.color.onSurface, fontWeight: '600', marginTop: 2 },
  actionsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 4 },
  errorBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: tokens.color.errorBg, borderColor: tokens.color.error, borderWidth: 1,
    padding: 12, borderRadius: tokens.radius.md,
  },
  errorText: { flex: 1, color: tokens.color.onSurface, fontSize: 13 },
  overlay: {
    position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
    backgroundColor: tokens.color.scrim,
    alignItems: 'center', justifyContent: 'center', padding: 24,
  },
  confirmCard: {
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: tokens.radius.lg,
    padding: tokens.spacing.lg,
    borderWidth: 1, borderColor: tokens.color.borderStrong,
    maxWidth: 380, width: '100%',
  },
  confirmTitle: { fontSize: 17, fontWeight: '700', color: tokens.color.onSurface },
  confirmBody: { fontSize: 13, color: tokens.color.onSurfaceMuted, lineHeight: 19, marginTop: 8 },
  pressed: { opacity: 0.7 },
});
