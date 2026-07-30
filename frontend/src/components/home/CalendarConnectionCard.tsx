import { useCallback, useState } from 'react';
import { View, Text, StyleSheet, Linking, Platform, ActivityIndicator } from 'react-native';
import Animated, { FadeInDown, FadeIn } from 'react-native-reanimated';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import { tokens } from '@/src/theme/tokens';
import { api, ConnectorInstance } from '@/src/api/client';
import { ActionBtn } from '@/src/components/ui/ActionBtn';
import { haptic } from '@/src/utils/haptic';
import { humanizeError } from '@/src/utils/errors';
import { formatRelativeAgo } from '@/src/utils/labels';

type Props = {
  instance: ConnectorInstance | null;   // A: null, B/C: object
  eventsIngested?: number;
  onAfterSync?: () => void;             // parent reloads home
  onAfterConnect?: () => void;          // parent reloads home
};

type SyncStep = 'idle' | 'connecting' | 'importing' | 'updating' | 'done';

const STEP_TEXT: Record<SyncStep, string> = {
  idle: '',
  connecting: 'Connessione…',
  importing: 'Importazione eventi…',
  updating: 'Aggiornamento ORA…',
  done: 'Completato',
};

export function CalendarConnectionCard({ instance, eventsIngested, onAfterSync, onAfterConnect }: Props) {
  const router = useRouter();
  const [connecting, setConnecting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [step, setStep] = useState<SyncStep>('idle');
  const [progress, setProgress] = useState(0); // 0..1
  const [error, setError] = useState<string | null>(null);
  const [lastSyncResult, setLastSyncResult] = useState<{ processed: number; skipped: number } | null>(null);

  const hasInstance = !!instance;
  const neverSynced = hasInstance && !instance!.last_sync_at;

  // --------- OAuth start
  const startConnect = useCallback(async () => {
    setError(null);
    haptic('tap');
    setConnecting(true);
    try {
      const r = await api.googleCalendarOAuthStart();
      const url = r.authorize_url;
      if (!url) throw new Error('connect_failed');
      if (Platform.OS === 'web') {
        const win: any = typeof window !== 'undefined' ? window : null;
        if (win) win.location.assign(url);
        else await Linking.openURL(url);
      } else {
        const supported = await Linking.canOpenURL(url);
        if (!supported) throw new Error('cannot_open_url');
        await Linking.openURL(url);
      }
    } catch (e: any) {
      haptic('error');
      setError(humanizeError(e, 'connect'));
    } finally {
      setConnecting(false);
    }
  }, []);

  // --------- Sync now
  const startSync = useCallback(async () => {
    if (!instance) return;
    setError(null);
    setLastSyncResult(null);
    haptic('medium');
    setSyncing(true);
    setStep('connecting');
    setProgress(0.15);
    let stepTimer: any = null;
    try {
      // Progressive UI: give the user something to watch even if backend is fast
      stepTimer = setTimeout(() => { setStep('importing'); setProgress(0.5); }, 400);
      const res = await api.googleCalendarSync(instance.id);
      clearTimeout(stepTimer);
      setStep('updating');
      setProgress(0.85);
      // short delay so user perceives step transition
      await new Promise((r) => setTimeout(r, 350));
      setStep('done');
      setProgress(1);
      setLastSyncResult({
        processed: res.total_events_processed || 0,
        skipped: res.total_events_skipped || 0,
      });
      haptic('success');
      onAfterSync?.();
      setTimeout(() => { setStep('idle'); setSyncing(false); setProgress(0); }, 1400);
    } catch (e: any) {
      clearTimeout(stepTimer);
      haptic('error');
      setError(humanizeError(e, 'sync'));
      setStep('idle');
      setProgress(0);
      setSyncing(false);
    }
  }, [instance, onAfterSync]);

  // --------- STATE A — non connesso (Hero)
  if (!hasInstance) {
    return (
      <Animated.View entering={FadeInDown.duration(tokens.motion.slow)} style={styles.heroCard} testID="calendar-hero">
        <View style={styles.heroIconWrap}>
          <Ionicons name="calendar-outline" size={28} color={tokens.color.brand} />
        </View>
        <Text style={styles.heroTitle} accessibilityRole="header">Collega il tuo Google Calendar</Text>
        <Text style={styles.heroBody}>
          ORA può capire automaticamente i tuoi impegni e aiutarti a organizzare la giornata.
        </Text>
        {error ? <Text style={styles.errorText}>{error}</Text> : null}
        <View style={styles.heroActions}>
          <ActionBtn
            primary
            icon="logo-google"
            label={connecting ? 'Apro Google…' : 'Continua con Google'}
            onPress={startConnect}
            loading={connecting}
            testID="btn-connect-google"
            accessibilityHint="Apri Google per collegare il tuo calendario"
          />
          <ActionBtn
            variant="ghost"
            icon="information-circle-outline"
            label="Scopri come funziona"
            onPress={() => { haptic('tap'); router.push('/how-it-works'); }}
            testID="btn-how-it-works"
          />
        </View>
      </Animated.View>
    );
  }

  // --------- STATE B — connesso ma mai sincronizzato
  if (neverSynced && !lastSyncResult) {
    return (
      <Animated.View entering={FadeInDown.duration(tokens.motion.slow)} style={styles.card} testID="calendar-connected-nosync">
        <View style={styles.rowHead}>
          <View style={styles.badgeOk}>
            <Ionicons name="checkmark-circle" size={16} color={tokens.color.success} />
            <Text style={styles.badgeOkText}>Google Calendar collegato</Text>
          </View>
        </View>
        <Text style={styles.body}>Premi Sincronizza per importare i tuoi eventi.</Text>
        {syncing ? (
          <SyncProgress step={step} progress={progress} />
        ) : null}
        {error ? <Text style={styles.errorText}>{error}</Text> : null}
        <View style={styles.actionsRow}>
          <ActionBtn
            primary
            icon="sync"
            label={syncing ? 'Sincronizzo…' : 'Sincronizza ora'}
            onPress={startSync}
            loading={syncing}
            disabled={syncing}
            testID="btn-sync-now"
          />
        </View>
      </Animated.View>
    );
  }

  // --------- STATE C — connesso e sincronizzato
  const nCalendars = instance!.selected_resource_ids?.length || 0;
  const lastSync = instance!.last_sync_at ? new Date(instance!.last_sync_at) : null;
  const lastLabel = lastSync ? formatRelativeAgo(lastSync) : '—';

  return (
    <Animated.View entering={FadeInDown.duration(tokens.motion.slow)} style={styles.card} testID="calendar-connected-synced">
      <View style={styles.rowHead}>
        <View style={styles.badgeOk}>
          <Ionicons name="checkmark-circle" size={16} color={tokens.color.success} />
          <Text style={styles.badgeOkText}>Google Calendar collegato</Text>
        </View>
      </View>
      <View style={styles.statsRow}>
        <Stat icon="time-outline" label="Aggiornato" value={lastLabel} />
        <Stat icon="albums-outline" label="Calendari" value={String(nCalendars)} />
        {typeof eventsIngested === 'number' ? (
          <Stat icon="calendar-outline" label="Eventi" value={String(eventsIngested)} />
        ) : null}
      </View>
      {syncing ? <SyncProgress step={step} progress={progress} /> : null}
      {lastSyncResult && !syncing ? (
        <Animated.View entering={FadeIn.duration(tokens.motion.base)} style={styles.resultRow}>
          <Ionicons name="checkmark-done-outline" size={14} color={tokens.color.success} />
          <Text style={styles.resultText}>
            {lastSyncResult.processed} nuovi · {lastSyncResult.skipped} già presenti
          </Text>
        </Animated.View>
      ) : null}
      {error ? <Text style={styles.errorText}>{error}</Text> : null}
      <View style={styles.actionsRow}>
        <ActionBtn
          primary
          icon="sync"
          label={syncing ? 'Sincronizzo…' : 'Sincronizza'}
          onPress={startSync}
          loading={syncing}
          disabled={syncing}
          testID="btn-sync"
        />
        <ActionBtn
          variant="ghost"
          icon="options-outline"
          label="Gestisci calendari"
          onPress={() => { haptic('tap'); router.push(`/manage-calendars?instance=${instance!.id}`); }}
          testID="btn-manage-calendars"
        />
        <ActionBtn
          variant="ghost"
          icon="settings-outline"
          label="Impostazioni"
          onPress={() => { haptic('tap'); router.push('/settings'); }}
          testID="btn-open-settings"
        />
      </View>
    </Animated.View>
  );
}

function Stat({ icon, label, value }: { icon: any; label: string; value: string }) {
  return (
    <View style={styles.stat} accessible accessibilityLabel={`${label}: ${value}`}>
      <Ionicons name={icon} size={13} color={tokens.color.onSurfaceMuted} />
      <View>
        <Text style={styles.statLabel}>{label}</Text>
        <Text style={styles.statValue}>{value}</Text>
      </View>
    </View>
  );
}

function SyncProgress({ step, progress }: { step: SyncStep; progress: number }) {
  return (
    <View style={styles.progressBox} accessibilityRole="progressbar" accessibilityLabel="Sincronizzazione in corso">
      <View style={styles.progressRow}>
        {step !== 'done' ? (
          <ActivityIndicator size="small" color={tokens.color.brand} />
        ) : (
          <Ionicons name="checkmark-circle" size={16} color={tokens.color.success} />
        )}
        <Text style={styles.progressText}>{STEP_TEXT[step]}</Text>
      </View>
      <View style={styles.progressTrack}>
        <Animated.View
          entering={FadeIn.duration(tokens.motion.fast)}
          style={[styles.progressBar, { width: `${Math.round(progress * 100)}%` }]}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  // A — Hero
  heroCard: {
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: tokens.radius.lg,
    padding: tokens.spacing.xl,
    gap: 10,
    borderWidth: 1,
    borderColor: tokens.color.borderStrong,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.25,
    shadowRadius: 12,
    elevation: 4,
  },
  heroIconWrap: {
    width: 56, height: 56, borderRadius: 28,
    backgroundColor: tokens.color.surfaceTertiary,
    alignItems: 'center', justifyContent: 'center',
    marginBottom: 4,
  },
  heroTitle: { fontSize: 20, fontWeight: '700', color: tokens.color.onSurface, textAlign: 'center' },
  heroBody: { fontSize: 14, color: tokens.color.onSurfaceMuted, textAlign: 'center', lineHeight: 20, maxWidth: 320 },
  heroActions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 8, justifyContent: 'center' },

  // B/C card
  card: {
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: tokens.radius.lg,
    padding: tokens.spacing.lg,
    gap: 10,
    borderWidth: 1,
    borderColor: tokens.color.border,
  },
  rowHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  badgeOk: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  badgeOkText: { fontSize: 14, color: tokens.color.onSurface, fontWeight: '600' },
  body: { fontSize: 13, color: tokens.color.onSurfaceMuted, lineHeight: 19 },

  statsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginTop: 4 },
  stat: { flexDirection: 'row', alignItems: 'center', gap: 6, minWidth: 100 },
  statLabel: { fontSize: 10, color: tokens.color.onSurfaceMuted, textTransform: 'uppercase', letterSpacing: 0.5 },
  statValue: { fontSize: 14, color: tokens.color.onSurface, fontWeight: '600', marginTop: 1 },

  actionsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 4 },
  progressBox: {
    backgroundColor: tokens.color.surfaceTertiary,
    padding: 10,
    borderRadius: tokens.radius.md,
    gap: 8,
  },
  progressRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  progressText: { fontSize: 13, color: tokens.color.onSurface, fontWeight: '500' },
  progressTrack: { width: '100%', height: 6, borderRadius: 3, backgroundColor: tokens.color.surface, overflow: 'hidden' },
  progressBar: { height: 6, borderRadius: 3, backgroundColor: tokens.color.brand },
  resultRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  resultText: { fontSize: 12, color: tokens.color.onSurfaceMuted, fontWeight: '500' },
  errorText: { fontSize: 13, color: tokens.color.error, lineHeight: 18 },
});
