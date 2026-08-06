import { useCallback, useEffect, useRef, useState } from 'react';
import { View, ScrollView, RefreshControl, Text, StyleSheet, Modal, Pressable, TextInput } from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { useFocusEffect, useRouter } from 'expo-router';

import { tokens } from '@/src/theme/tokens';
import {
  api, HomeV2Response, HomeActionDef, HomePriorityBand,
} from '@/src/api/client';
import { haptic } from '@/src/utils/haptic';
import { useOnlineStatus, isNetworkError } from '@/src/hooks/use-online-status';
import { humanizeError } from '@/src/utils/errors';
import { FocusSkeleton } from '@/src/components/Skeleton';
import { HomeHeader, OfflineBanner, ErrorBanner } from '@/src/components/home/HomeHeader';
import { AdessoCard } from '@/src/components/home/v2/AdessoCard';
import { PercheAdesso } from '@/src/components/home/v2/PercheAdesso';
import { DynamicActions } from '@/src/components/home/v2/DynamicActions';
import { SituazioneCard } from '@/src/components/home/v2/SituazioneCard';
import { GoogleBanner } from '@/src/components/home/v2/GoogleBanner';
import { PrioritaList } from '@/src/components/home/v2/PrioritaList';
import { OraOsserva } from '@/src/components/home/v2/OraOsserva';
import { OraTiConsiglia } from '@/src/components/home/v2/OraTiConsiglia';
import { ParlaConOra } from '@/src/components/home/v2/ParlaConOra';
import { ResumeCard } from '@/src/components/home/v2/ResumeCard';
import { EmptyHome } from '@/src/components/home/v2/EmptyHome';

const CONTAINER_MAX_WIDTH = 720;

export default function HomeScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [home, setHome] = useState<HomeV2Response | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastSuccessAt, setLastSuccessAt] = useState<Date | null>(null);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [suggestionBusy, setSuggestionBusy] = useState<string | null>(null);
  const [correctOpen, setCorrectOpen] = useState(false);
  const [snoozeOpen, setSnoozeOpen] = useState(false);
  const [pendingItemId, setPendingItemId] = useState<string | null>(null);
  const { online, markOffline, markOnline } = useOnlineStatus();
  const inflight = useRef(false);

  const load = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) setLoading(true);
    try {
      const data = await api.getHome();
      setHome(data);
      markOnline();
      setLastSuccessAt(new Date());
      setErrorBanner(null);
    } catch (e: any) {
      if (isNetworkError(e)) markOffline();
      else setErrorBanner(humanizeError(e, 'default'));
    } finally {
      setLoading(false);
    }
  }, [markOffline, markOnline]);

  useEffect(() => { load(); }, [load]);
  useFocusEffect(useCallback(() => { load({ silent: true }); }, [load]));

  const runHomeAction = useCallback(async (
    itemId: string,
    action: string,
    extra?: { until?: string; priority?: HomePriorityBand; reason?: string },
  ) => {
    if (inflight.current) return;
    inflight.current = true;
    setActionBusy(action);
    setErrorBanner(null);
    try {
      await api.homeAction({ item_id: itemId, action, ...extra });
      haptic('success');
      await load({ silent: true });
    } catch (e: any) {
      if (isNetworkError(e)) markOffline();
      setErrorBanner(humanizeError(e, 'default'));
      haptic('error');
    } finally {
      inflight.current = false;
      setActionBusy(null);
    }
  }, [load, markOffline]);

  const onDynamicAction = useCallback(async (action: HomeActionDef) => {
    const focus = home?.primary_focus;
    if (!focus) return;
    haptic('tap');
    if (action.kind === 'snooze') {
      setPendingItemId(focus.id);
      setSnoozeOpen(true);
      return;
    }
    if (action.kind === 'correct') {
      setPendingItemId(focus.id);
      setCorrectOpen(true);
      return;
    }
    if (['maps', 'navigate', 'open', 'guide', 'study', 'resume', 'confirm'].includes(action.kind)) {
      // navigation / ActionEngine handled in DynamicActions; record open/resume
      if (action.kind === 'resume' || action.kind === 'open' || action.kind === 'guide') {
        await runHomeAction(focus.id, action.kind === 'resume' ? 'resume' : 'open');
      }
      return;
    }
    await runHomeAction(focus.id, action.kind === 'complete' ? 'complete' : action.kind);
  }, [home?.primary_focus, runHomeAction]);

  const onRefresh = useCallback(async () => {
    haptic('select');
    setRefreshing(true);
    try {
      const data = await api.refreshHome();
      setHome(data);
      markOnline();
      setLastSuccessAt(new Date());
    } catch (e: any) {
      if (isNetworkError(e)) markOffline();
      await load({ silent: true });
    } finally {
      setRefreshing(false);
    }
  }, [load, markOffline, markOnline]);

  const focus = home?.primary_focus || null;
  const showGoogleBanner = !!home?.google_calendar?.show_banner;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: tokens.color.surface }} edges={['top']} testID="home-safe">
      <ScrollView
        contentContainerStyle={{
          padding: tokens.spacing.lg,
          gap: tokens.spacing.lg,
          maxWidth: CONTAINER_MAX_WIDTH,
          width: '100%',
          alignSelf: 'center',
          paddingBottom: Math.max(insets.bottom, 16) + 108,
        }}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={tokens.color.onSurface}
            colors={[tokens.color.onSurface]}
            progressBackgroundColor={tokens.color.surfaceSecondary}
          />
        }
        showsVerticalScrollIndicator={false}
        testID="home-scroll"
      >
        <ParlaConOra onError={(msg) => setErrorBanner(msg)} />
        <HomeHeader online={online} lastSuccessAt={lastSuccessAt} />
        {!online ? <OfflineBanner /> : null}
        {errorBanner ? <ErrorBanner message={errorBanner} onDismiss={() => setErrorBanner(null)} /> : null}
        {home?.partial ? (
          <View style={styles.warn} testID="partial-warning">
            <Text style={styles.warnText}>Alcune fonti non sono disponibili. Mostro i dati parziali.</Text>
          </View>
        ) : null}

        {loading ? (
          <FocusSkeleton />
        ) : focus ? (
          <Animated.View entering={FadeInDown.duration(tokens.motion.slow)} style={{ gap: tokens.spacing.md }}>
            <AdessoCard item={focus} />
            {home?.explanation ? (
              <PercheAdesso
                explanation={home.explanation}
                onCorrect={() => { setPendingItemId(focus.id); setCorrectOpen(true); }}
                onIgnore={() => runHomeAction(focus.id, 'ignore')}
              />
            ) : null}
            <DynamicActions item={focus} busy={actionBusy} onAction={onDynamicAction} />
          </Animated.View>
        ) : (
          <EmptyHome />
        )}

        {!loading && home?.current_situation ? (
          <SituazioneCard
            situation={home.current_situation}
            onOpen={() => { haptic('tap'); router.push('/situazione'); }}
          />
        ) : null}

        {!loading ? (
          <GoogleBanner
            visible={showGoogleBanner}
            onDismiss={() => runHomeAction('__google_banner__', 'dismiss_banner')}
            onConnected={() => load({ silent: true })}
          />
        ) : null}

        {!loading && home?.priorities ? <PrioritaList groups={home.priorities} /> : null}

        {!loading && (home?.ora_ti_consiglia?.length ?? 0) > 0 ? (
          <OraTiConsiglia
            suggestions={home!.ora_ti_consiglia!}
            busyId={suggestionBusy}
            onAccept={async (id) => {
              setSuggestionBusy(id);
              try {
                const res = await api.acceptSuggestion(id);
                haptic('success');
                const r = (res.result || {}) as Record<string, unknown>;
                // Conversation handoff → AE guided UI (never chat)
                const route =
                  (r.route as string | undefined) ||
                  ((r.result as any)?.route as string | undefined);
                await load({ silent: true });
                if (route) router.push(route as any);
              } catch (e: any) {
                if (isNetworkError(e)) markOffline();
                setErrorBanner(humanizeError(e, 'default'));
                haptic('error');
              } finally {
                setSuggestionBusy(null);
              }
            }}
            onDismiss={async (id) => {
              setSuggestionBusy(id);
              try {
                await api.dismissSuggestion(id);
                haptic('success');
                await load({ silent: true });
              } catch (e: any) {
                if (isNetworkError(e)) markOffline();
                setErrorBanner(humanizeError(e, 'default'));
              } finally {
                setSuggestionBusy(null);
              }
            }}
            onSnooze={async (id, preset) => {
              setSuggestionBusy(id);
              try {
                await api.snoozeSuggestion(id, { preset });
                haptic('success');
                await load({ silent: true });
              } catch (e: any) {
                if (isNetworkError(e)) markOffline();
                setErrorBanner(humanizeError(e, 'default'));
              } finally {
                setSuggestionBusy(null);
              }
            }}
            onOpen={(s) => {
              if (s.action?.route) router.push(s.action.route as any);
            }}
          />
        ) : null}

        {!loading && home?.insights ? (
          <OraOsserva
            insights={home.insights}
            onIgnore={(id) => runHomeAction(id, 'ignore')}
            onAction={(ins) => {
              if (ins.action?.route) router.push(ins.action.route as any);
              runHomeAction(ins.id, 'mark_insight_read');
            }}
          />
        ) : null}

        {!loading && home?.resume_item ? (
          <ResumeCard
            item={home.resume_item}
            onResume={() => runHomeAction(home.resume_item!.id, 'resume')}
          />
        ) : null}
      </ScrollView>

      <CorrectPriorityModal
        open={correctOpen}
        onClose={() => setCorrectOpen(false)}
        onPick={(p) => {
          if (pendingItemId) runHomeAction(pendingItemId, 'correct', { priority: p });
          setCorrectOpen(false);
        }}
      />
      <SnoozeModal
        open={snoozeOpen}
        onClose={() => setSnoozeOpen(false)}
        onSubmit={(until) => {
          if (pendingItemId) runHomeAction(pendingItemId, 'snooze', { until });
          setSnoozeOpen(false);
        }}
      />
    </SafeAreaView>
  );
}

function CorrectPriorityModal({
  open, onClose, onPick,
}: {
  open: boolean;
  onClose: () => void;
  onPick: (p: HomePriorityBand) => void;
}) {
  const opts: HomePriorityBand[] = ['critical', 'today', 'this_week', 'waiting', 'later'];
  const labels: Record<HomePriorityBand, string> = {
    critical: 'Critico', today: 'Oggi', this_week: 'Questa settimana', waiting: 'In attesa', later: 'Più avanti',
  };
  return (
    <Modal visible={open} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.modalScrim} onPress={onClose}>
        <View style={styles.modalCard}>
          <Text style={styles.modalTitle}>Correggi priorità</Text>
          {opts.map((p) => (
            <Pressable key={p} style={styles.modalRow} onPress={() => onPick(p)} testID={`correct-${p}`}>
              <Text style={styles.modalRowText}>{labels[p]}</Text>
            </Pressable>
          ))}
        </View>
      </Pressable>
    </Modal>
  );
}

function SnoozeModal({
  open, onClose, onSubmit,
}: {
  open: boolean;
  onClose: () => void;
  onSubmit: (until: string) => void;
}) {
  const [hours, setHours] = useState('4');
  return (
    <Modal visible={open} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.modalScrim} onPress={onClose}>
        <View style={styles.modalCard} onStartShouldSetResponder={() => true}>
          <Text style={styles.modalTitle}>Rimanda (ore)</Text>
          <TextInput
            style={styles.input}
            value={hours}
            onChangeText={setHours}
            keyboardType="number-pad"
            testID="snooze-hours"
          />
          <Pressable
            style={styles.modalRow}
            onPress={() => {
              const h = Math.max(1, parseInt(hours || '4', 10) || 4);
              const until = new Date(Date.now() + h * 3600_000).toISOString();
              onSubmit(until);
            }}
            testID="snooze-confirm"
          >
            <Text style={styles.modalRowText}>Conferma</Text>
          </Pressable>
        </View>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  warn: {
    backgroundColor: tokens.color.warningBg,
    borderColor: tokens.color.warning,
    borderWidth: 1,
    borderRadius: tokens.radius.md,
    padding: 12,
  },
  warnText: { color: tokens.color.onSurface, fontSize: 13 },
  modalScrim: {
    flex: 1, backgroundColor: tokens.color.scrim,
    justifyContent: 'center', padding: 24,
  },
  modalCard: {
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: tokens.radius.lg,
    padding: 16,
    gap: 8,
    borderWidth: 1,
    borderColor: tokens.color.border,
  },
  modalTitle: { fontSize: 16, fontWeight: '700', color: tokens.color.onSurface, marginBottom: 4 },
  modalRow: {
    paddingVertical: 12, paddingHorizontal: 8,
    borderRadius: tokens.radius.md, backgroundColor: tokens.color.surfaceTertiary,
  },
  modalRowText: { color: tokens.color.onSurface, fontSize: 14, fontWeight: '600' },
  input: {
    borderWidth: 1, borderColor: tokens.color.borderStrong,
    borderRadius: tokens.radius.md, padding: 12,
    color: tokens.color.onSurface, backgroundColor: tokens.color.surfaceTertiary,
  },
});
