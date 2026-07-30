/**
 * ORA — Iterazione 18
 * Connetti Apple Calendar (EventKit) — flusso end-to-end iPhone/iPad.
 *
 * Flusso (thumb-friendly, one-hand):
 *   1) Intro & pre-permission explanation (perché serve, cosa leggiamo)
 *   2) Prompt permessi nativi (contestuale, dopo tap "Consenti accesso")
 *   3) Selezione calendari (multi-check)
 *   4) Batch upload verso backend /sync
 *   5) Stato "sincronizzato" con conteggi (processed / mirrored / quarantined)
 *
 * Denial handling:
 *   - Se denied + canAskAgain=true: mostra CTA "Riprova"
 *   - Se denied + canAskAgain=false: mostra CTA "Apri Impostazioni" con Linking.openSettings()
 *   - Se piattaforma non supportata: banner informativo (nessun dead-end)
 */
import { useCallback, useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator, Linking, Platform,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { Stack, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import Animated, { FadeInDown, FadeIn } from 'react-native-reanimated';
import * as Application from 'expo-constants';

import { tokens } from '@/src/theme/tokens';
import { api, AppleCalendarInfo, AppleCalendarSyncResult } from '@/src/api/client';
import { humanizeError } from '@/src/utils/errors';
import { haptic } from '@/src/utils/haptic';
import { ActionBtn } from '@/src/components/ui/ActionBtn';
import * as AppleCalendar from '@/src/utils/apple-calendar';

type Step = 'intro' | 'permission_denied' | 'permission_blocked' | 'select' | 'syncing' | 'done';

export default function ConnectAppleCalendarScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [step, setStep] = useState<Step>('intro');
  const [, setPermission] = useState<AppleCalendar.PermissionResult | null>(null);
  const [calendars, setCalendars] = useState<AppleCalendarInfo[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [syncResult, setSyncResult] = useState<AppleCalendarSyncResult | null>(null);

  const supported = AppleCalendar.isSupported();

  // On mount, check current permission state so we can skip the intro
  // when access has already been granted (contextual UX).
  useEffect(() => {
    (async () => {
      const p = await AppleCalendar.getPermissionStatus();
      setPermission(p);
      if (p.status === 'granted') {
        await loadCalendars();
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadCalendars = useCallback(async () => {
    setError(null);
    setBusy(true);
    try {
      const items = await AppleCalendar.listCalendars();
      setCalendars(items);
      // Default: select all calendars — user can uncheck if too noisy.
      setSelected(new Set(items.map(c => c.id)));
      setStep('select');
    } catch (e: any) {
      setError(humanizeError(e));
    } finally {
      setBusy(false);
    }
  }, []);

  const onAllowAccess = async () => {
    haptic('tap');
    if (!supported) {
      setError('Apple Calendar è disponibile solo su iPhone e iPad.');
      return;
    }
    setBusy(true);
    try {
      const p = await AppleCalendar.requestPermission();
      setPermission(p);
      if (p.status === 'granted') {
        haptic('success');
        await loadCalendars();
      } else if (p.status === 'denied') {
        haptic('warning');
        setStep(p.canAskAgain ? 'permission_denied' : 'permission_blocked');
      }
    } catch (e: any) {
      setError(humanizeError(e));
    } finally {
      setBusy(false);
    }
  };

  const toggle = (id: string) => {
    haptic('tap');
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const onConfirm = async () => {
    haptic('medium');
    if (selected.size === 0) {
      setError('Seleziona almeno un calendario per continuare.');
      return;
    }
    setStep('syncing');
    setBusy(true);
    setError(null);
    try {
      const deviceId = getStableDeviceId();
      const deviceName = getDeviceName();
      const calendarsToSend: AppleCalendarInfo[] = calendars.filter(c => selected.has(c.id));

      // 1) Register / refresh the connector instance.
      const connectRes = await api.appleCalendarConnect({
        device_id: deviceId,
        device_name: deviceName,
        platform: Platform.OS === 'ios' ? 'ios' : undefined,
        calendars: calendarsToSend,
      });
      const instance = connectRes.instance;

      // 2) Read the actual events from the device.
      const events = await AppleCalendar.readEvents(Array.from(selected), {
        pastDays: 30, futureDays: 180,
      });

      // 3) Push in chunks so a single sync of 1000+ events never hits
      //    a payload limit. Backend is idempotent so retrying a chunk
      //    is safe.
      const totals = { received: 0, processed: 0, skipped: 0, mirrored: 0, quarantined: 0, failed: 0 };
      const CHUNK = 200;
      for (let i = 0; i < events.length; i += CHUNK) {
        const chunk = events.slice(i, i + CHUNK);
        const res = await api.appleCalendarSync(instance.id, chunk);
        totals.received  += res.totals.received;
        totals.processed += res.totals.processed;
        totals.skipped   += res.totals.skipped;
        totals.mirrored  += res.totals.mirrored;
        totals.quarantined += res.totals.quarantined;
        totals.failed    += res.totals.failed;
      }
      setSyncResult({ instance_id: instance.id, totals, outcomes: [] });
      setStep('done');
      haptic('success');
    } catch (e: any) {
      haptic('error');
      setError(humanizeError(e, 'sync'));
      setStep('select');
    } finally {
      setBusy(false);
    }
  };

  const onOpenSettings = () => {
    haptic('tap');
    Linking.openSettings();
  };

  const totalSelected = selected.size;
  const canConfirm = totalSelected > 0 && !busy;

  return (
    <SafeAreaView style={styles.safe} edges={['top']} testID="connect-apple-calendar">
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Pressable
          onPress={() => { haptic('tap'); router.back(); }}
          style={({ pressed }) => [styles.backBtn, pressed && styles.pressed]}
          accessibilityRole="button" accessibilityLabel="Torna indietro" hitSlop={12}
        >
          <Ionicons name="chevron-back" size={22} color={tokens.color.onSurface} />
        </Pressable>
        <Text style={styles.title}>Apple Calendar</Text>
        <View style={{ width: 32 }} />
      </View>

      <ScrollView
        contentContainerStyle={{ padding: 20, paddingBottom: insets.bottom + 32, gap: 16 }}
        showsVerticalScrollIndicator={false}
      >
        {!supported ? (
          <UnsupportedBanner />
        ) : null}

        {step === 'intro' && supported && (
          <IntroCard onAllow={onAllowAccess} busy={busy} />
        )}

        {step === 'permission_denied' && (
          <DeniedCard onRetry={onAllowAccess} busy={busy} />
        )}

        {step === 'permission_blocked' && (
          <BlockedCard onOpenSettings={onOpenSettings} />
        )}

        {step === 'select' && (
          <SelectCalendars
            calendars={calendars}
            selected={selected}
            onToggle={toggle}
            onConfirm={onConfirm}
            busy={busy}
            canConfirm={canConfirm}
          />
        )}

        {step === 'syncing' && <SyncingCard />}

        {step === 'done' && syncResult && (
          <DoneCard result={syncResult} onFinish={() => { haptic('tap'); router.replace('/settings'); }} />
        )}

        {error ? (
          <Animated.View entering={FadeIn.duration(180)} style={styles.errorBanner} testID="apple-cal-error">
            <Ionicons name="alert-circle" size={16} color={tokens.color.error} />
            <Text style={styles.errorText}>{error}</Text>
          </Animated.View>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

// -------------------------------------------------------------
// UI blocks
// -------------------------------------------------------------
function UnsupportedBanner() {
  return (
    <Animated.View entering={FadeInDown.duration(220)} style={styles.card}>
      <View style={styles.cardHead}>
        <View style={styles.iconWrap}>
          <Ionicons name="phone-portrait-outline" size={18} color={tokens.color.info} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.cardTitle}>Solo iPhone e iPad</Text>
          <Text style={styles.cardMeta}>
            Il calendario nativo Apple si legge tramite EventKit, disponibile solo su iOS/iPadOS.
            Su Android o Web usa il connettore Google Calendar.
          </Text>
        </View>
      </View>
    </Animated.View>
  );
}

function IntroCard({ onAllow, busy }: { onAllow: () => void; busy: boolean }) {
  return (
    <Animated.View entering={FadeInDown.duration(220)} style={styles.card} testID="apple-cal-intro">
      <View style={styles.cardHead}>
        <View style={styles.iconWrap}>
          <Ionicons name="calendar-outline" size={18} color={tokens.color.brand} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.cardTitle}>Collega il tuo calendario</Text>
          <Text style={styles.cardMeta}>
            ORA legge gli eventi del tuo iPhone per aiutarti a organizzare la giornata.
          </Text>
        </View>
      </View>

      <View style={styles.bulletsGroup}>
        <Bullet icon="lock-closed-outline" title="Solo lettura" desc="Non modifichiamo o cancelliamo nulla nel tuo calendario." />
        <Bullet icon="phone-portrait-outline" title="I dati restano tuoi" desc="Gli eventi vengono elaborati per te. Puoi revocare l'accesso in qualsiasi momento." />
        <Bullet icon="git-compare-outline" title="Zero duplicati" desc="Se hai già collegato Google Calendar, gli eventi presenti su entrambi non verranno duplicati." />
      </View>

      <ActionBtn
        primary
        icon="checkmark-circle-outline"
        label="Consenti accesso al calendario"
        onPress={onAllow}
        loading={busy}
        testID="btn-allow-apple-calendar"
      />
    </Animated.View>
  );
}

function Bullet({ icon, title, desc }: { icon: keyof typeof Ionicons.glyphMap; title: string; desc: string }) {
  return (
    <View style={styles.bulletRow}>
      <View style={styles.bulletIcon}><Ionicons name={icon} size={16} color={tokens.color.onSurface} /></View>
      <View style={{ flex: 1 }}>
        <Text style={styles.bulletTitle}>{title}</Text>
        <Text style={styles.bulletDesc}>{desc}</Text>
      </View>
    </View>
  );
}

function DeniedCard({ onRetry, busy }: { onRetry: () => void; busy: boolean }) {
  return (
    <Animated.View entering={FadeInDown.duration(220)} style={styles.card}>
      <View style={styles.cardHead}>
        <View style={styles.iconWrap}>
          <Ionicons name="warning-outline" size={18} color={tokens.color.warning} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.cardTitle}>Accesso non concesso</Text>
          <Text style={styles.cardMeta}>
            Senza accesso al calendario, ORA non può proporti le priorità della giornata basate sui tuoi impegni.
          </Text>
        </View>
      </View>
      <ActionBtn primary icon="refresh" label="Riprova" onPress={onRetry} loading={busy} />
    </Animated.View>
  );
}

function BlockedCard({ onOpenSettings }: { onOpenSettings: () => void }) {
  return (
    <Animated.View entering={FadeInDown.duration(220)} style={styles.card}>
      <View style={styles.cardHead}>
        <View style={styles.iconWrap}>
          <Ionicons name="settings-outline" size={18} color={tokens.color.info} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.cardTitle}>Autorizzalo dalle Impostazioni</Text>
          <Text style={styles.cardMeta}>
            Il permesso è stato bloccato. Aprilo manualmente da Impostazioni → Privacy → Calendari → ORA.
          </Text>
        </View>
      </View>
      <ActionBtn primary icon="open-outline" label="Apri Impostazioni" onPress={onOpenSettings} />
    </Animated.View>
  );
}

function SelectCalendars({
  calendars, selected, onToggle, onConfirm, busy, canConfirm,
}: {
  calendars: AppleCalendarInfo[];
  selected: Set<string>;
  onToggle: (id: string) => void;
  onConfirm: () => void;
  busy: boolean;
  canConfirm: boolean;
}) {
  return (
    <Animated.View entering={FadeInDown.duration(220)} style={styles.card} testID="apple-cal-select">
      <Text style={styles.cardTitle}>Scegli quali calendari sincronizzare</Text>
      <Text style={styles.cardMeta}>
        Puoi cambiare selezione in qualsiasi momento dalle Impostazioni.
      </Text>

      {calendars.length === 0 ? (
        <View style={{ padding: 16, alignItems: 'center' }}>
          <ActivityIndicator color={tokens.color.onSurfaceMuted} />
          <Text style={[styles.cardMeta, { marginTop: 8 }]}>Nessun calendario disponibile.</Text>
        </View>
      ) : (
        <View style={{ gap: 8 }}>
          {calendars.map(cal => (
            <CalendarRow
              key={cal.id}
              calendar={cal}
              checked={selected.has(cal.id)}
              onToggle={() => onToggle(cal.id)}
            />
          ))}
        </View>
      )}

      <ActionBtn
        primary
        icon="sync"
        label={busy ? 'Sincronizzazione…' : `Sincronizza ${selected.size} calendari`}
        onPress={onConfirm}
        loading={busy}
        disabled={!canConfirm}
        testID="btn-confirm-apple-sync"
      />
    </Animated.View>
  );
}

function CalendarRow({
  calendar, checked, onToggle,
}: { calendar: AppleCalendarInfo; checked: boolean; onToggle: () => void }) {
  return (
    <Pressable
      onPress={onToggle}
      style={({ pressed }) => [
        styles.row,
        checked && styles.rowChecked,
        pressed && styles.pressed,
      ]}
      accessibilityRole="checkbox"
      accessibilityState={{ checked }}
      accessibilityLabel={calendar.title || calendar.id}
      testID={`cal-row-${calendar.id}`}
    >
      <View style={[styles.colorDot, calendar.color ? { backgroundColor: calendar.color } : null]} />
      <View style={{ flex: 1 }}>
        <Text style={styles.rowTitle}>{calendar.title || calendar.id}</Text>
        {calendar.source ? <Text style={styles.rowMeta}>{calendar.source}</Text> : null}
      </View>
      <Ionicons
        name={checked ? 'checkmark-circle' : 'ellipse-outline'}
        size={22}
        color={checked ? tokens.color.success : tokens.color.onSurfaceMuted}
      />
    </Pressable>
  );
}

function SyncingCard() {
  return (
    <Animated.View entering={FadeInDown.duration(220)} style={styles.card}>
      <View style={{ alignItems: 'center', padding: 20 }}>
        <ActivityIndicator color={tokens.color.brand} />
        <Text style={[styles.cardTitle, { marginTop: 12 }]}>Sto leggendo gli eventi…</Text>
        <Text style={styles.cardMeta}>
          Lettura del calendario e trasferimento sicuro a ORA.
        </Text>
      </View>
    </Animated.View>
  );
}

function DoneCard({ result, onFinish }: { result: AppleCalendarSyncResult; onFinish: () => void }) {
  const { totals } = result;
  return (
    <Animated.View entering={FadeInDown.duration(220)} style={styles.card} testID="apple-cal-done">
      <View style={styles.cardHead}>
        <View style={styles.iconWrap}>
          <Ionicons name="checkmark-circle" size={20} color={tokens.color.success} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.cardTitle}>Calendario collegato</Text>
          <Text style={styles.cardMeta}>ORA ora usa i tuoi eventi per aiutarti.</Text>
        </View>
      </View>

      <View style={styles.metaGrid}>
        <MetaItem label="Eventi importati" value={String(totals.processed)} />
        {totals.mirrored > 0 ? (
          <MetaItem label="Già presenti (Google)" value={String(totals.mirrored)} />
        ) : null}
        {totals.skipped > 0 ? (
          <MetaItem label="Aggiornati" value={String(totals.skipped)} />
        ) : null}
        {totals.quarantined > 0 ? (
          <MetaItem label="Ignorati" value={String(totals.quarantined)} />
        ) : null}
      </View>

      <ActionBtn primary icon="checkmark" label="Fatto" onPress={onFinish} />
    </Animated.View>
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

// -------------------------------------------------------------
// Device identity helpers
// -------------------------------------------------------------
function getStableDeviceId(): string {
  // Prefer expo-constants' sessionId, which is stable per JS bundle
  // load — good enough for now. In a production build we could use
  // Application.getIosIdForVendorAsync() to get a per-device UUID.
  try {
    const anyC: any = Application as any;
    const sessionId = anyC?.default?.sessionId || anyC?.sessionId;
    if (sessionId) return `expo:${String(sessionId).slice(0, 32)}`;
  } catch {}
  return `expo:${Platform.OS}:${Date.now()}`;
}

function getDeviceName(): string {
  if (Platform.OS === 'ios') return 'iPhone';
  if (Platform.OS === 'android') return 'Android';
  return 'Web';
}

// -------------------------------------------------------------
// Styles
// -------------------------------------------------------------
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
  card: {
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: tokens.radius.lg,
    padding: tokens.spacing.lg,
    gap: 14,
    borderWidth: 1, borderColor: tokens.color.border,
  },
  cardHead: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  iconWrap: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: tokens.color.surfaceTertiary,
    alignItems: 'center', justifyContent: 'center',
  },
  cardTitle: { fontSize: 16, fontWeight: '700', color: tokens.color.onSurface },
  cardMeta: { fontSize: 13, color: tokens.color.onSurfaceMuted, marginTop: 2, lineHeight: 19 },
  bulletsGroup: { gap: 12, marginTop: 4 },
  bulletRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  bulletIcon: {
    width: 32, height: 32, borderRadius: 16,
    backgroundColor: tokens.color.surfaceTertiary,
    alignItems: 'center', justifyContent: 'center',
    marginTop: 2,
  },
  bulletTitle: { fontSize: 14, fontWeight: '600', color: tokens.color.onSurface },
  bulletDesc: { fontSize: 12, color: tokens.color.onSurfaceMuted, marginTop: 2, lineHeight: 17 },
  row: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    padding: 14,
    backgroundColor: tokens.color.surfaceTertiary,
    borderRadius: tokens.radius.md,
    borderWidth: 1, borderColor: tokens.color.border,
    minHeight: 56,
  },
  rowChecked: { borderColor: tokens.color.brand },
  rowTitle: { fontSize: 15, color: tokens.color.onSurface, fontWeight: '600' },
  rowMeta: { fontSize: 11, color: tokens.color.onSurfaceMuted, marginTop: 2 },
  colorDot: { width: 12, height: 12, borderRadius: 6, backgroundColor: tokens.color.onSurfaceMuted },
  metaGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 4 },
  metaBox: {
    minWidth: 120, flexGrow: 1, flexBasis: 120,
    backgroundColor: tokens.color.surfaceTertiary,
    padding: 10, borderRadius: tokens.radius.md,
  },
  metaLabel: { fontSize: 10, color: tokens.color.onSurfaceMuted, textTransform: 'uppercase', letterSpacing: 0.5 },
  metaValue: { fontSize: 14, color: tokens.color.onSurface, fontWeight: '600', marginTop: 2 },
  errorBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: tokens.color.errorBg, borderColor: tokens.color.error, borderWidth: 1,
    padding: 12, borderRadius: tokens.radius.md,
  },
  errorText: { flex: 1, color: tokens.color.onSurface, fontSize: 13 },
  pressed: { opacity: 0.7 },
});
