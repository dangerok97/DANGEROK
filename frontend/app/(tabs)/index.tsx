import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { View, ScrollView, RefreshControl } from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { FadeInDown, FadeOut, LinearTransition } from 'react-native-reanimated';
import { useFocusEffect } from 'expo-router';

import { tokens } from '@/src/theme/tokens';
import {
  api, ApiDecision, DecisionExplanation, DailySummary, ConnectorInstance,
  DecisionActionHistoryItem,
} from '@/src/api/client';
import { haptic } from '@/src/utils/haptic';
import { useOnlineStatus, isNetworkError } from '@/src/hooks/use-online-status';
import { humanizeError } from '@/src/utils/errors';
import { FocusSkeleton, DailySkeleton, LaterSkeleton } from '@/src/components/Skeleton';

import { HomeHeader, OfflineBanner, ErrorBanner } from '@/src/components/home/HomeHeader';
import { FocusNowCard } from '@/src/components/home/FocusNowCard';
import { DailySummaryCard } from '@/src/components/home/DailySummaryCard';
import { LaterList } from '@/src/components/home/LaterList';
import { EmptyFocus } from '@/src/components/home/EmptyFocus';
import { CalendarConnectionCard } from '@/src/components/home/CalendarConnectionCard';

import {
  WhyNowSheet, DailyDetailSheet, ConfirmSheet, PartialSheet,
  PostponeSheet, ReasonSheet, MoreMenu, HistorySheet,
} from '@/src/components/sheets/DecisionSheets';

type Flags = { explain: boolean; action: boolean; daily: boolean };

async function safe<T>(fn: () => Promise<T>): Promise<{ data?: T; error?: any; status?: number }> {
  try { return { data: await fn() }; }
  catch (e: any) { return { error: e, status: e?.status }; }
}

const CONTAINER_MAX_WIDTH = 720;

export default function HomeScreen() {
  const insets = useSafeAreaInsets();
  const [decisions, setDecisions] = useState<ApiDecision[]>([]);
  const [explanation, setExplanation] = useState<DecisionExplanation | null>(null);
  const [daily, setDaily] = useState<DailySummary | null>(null);
  const [instance, setInstance] = useState<ConnectorInstance | null>(null);
  const [flags, setFlags] = useState<Flags>({ explain: true, action: true, daily: true });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastSuccessAt, setLastSuccessAt] = useState<Date | null>(null);
  const [, setTick] = useState(0);
  const [whyOpen, setWhyOpen] = useState(false);
  const [dailyDetailOpen, setDailyDetailOpen] = useState(false);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [postponeOpen, setPostponeOpen] = useState(false);
  const [partialOpen, setPartialOpen] = useState(false);
  const [blockOpen, setBlockOpen] = useState(false);
  const [dismissOpen, setDismissOpen] = useState(false);
  const [confirmCompleteOpen, setConfirmCompleteOpen] = useState(false);
  const [moreMenuOpen, setMoreMenuOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [history, setHistory] = useState<DecisionActionHistoryItem[] | null>(null);
  const [otherWhy, setOtherWhy] = useState<DecisionExplanation | null>(null);
  const [otherWhyLoading, setOtherWhyLoading] = useState<string | null>(null);
  const { online, markOffline, markOnline } = useOnlineStatus();
  const inflight = useRef<Set<string>>(new Set());

  const activeDecisions = useMemo(
    () => decisions.filter((d) => !['completed', 'dismissed'].includes(d.status)),
    [decisions],
  );
  const focus = activeDecisions[0] || null;
  const later = activeDecisions.slice(1);

  const load = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) setLoading(true);
    const [decRes, dailyRes, calRes] = await Promise.all([
      safe(() => api.topDecisions(10)),
      safe(() => api.dailyToday()),
      safe(() => api.googleCalendarInstances()),
    ]);
    const allErrors = [decRes.error, dailyRes.error, calRes.error].filter(Boolean);
    const allNetwork = allErrors.length === 3 && allErrors.every(isNetworkError);
    if (allNetwork) markOffline();
    else { markOnline(); setLastSuccessAt(new Date()); }

    const items = decRes.data?.items || [];
    setDecisions(items);
    setDaily(dailyRes.data || null);
    const insts = calRes.data?.items || [];
    setInstance(insts[0] || null);

    if (items.length && flags.explain) {
      const exp = await safe(() => api.getExplanation(items[0].id));
      if (exp.status === 404 && String(exp.error?.detail?.detail || exp.error?.detail || '').includes('abilitata')) {
        setFlags((f) => ({ ...f, explain: false }));
        setExplanation(null);
      } else {
        setExplanation(exp.data || null);
      }
    } else {
      setExplanation(null);
    }
    setLoading(false);
  }, [flags.explain, markOffline, markOnline]);

  useEffect(() => { load(); }, [load]);

  // reload when returning from other screens (manage-calendars, settings, oauth callback)
  useFocusEffect(useCallback(() => { load({ silent: true }); }, [load]));

  useEffect(() => {
    const id = setInterval(() => setTick((n) => n + 1), 30_000);
    return () => clearInterval(id);
  }, []);

  const runAction = useCallback(async (
    key: string,
    fn: () => Promise<any>,
    opts?: { onDone?: () => void; hapticIntent?: 'tap' | 'medium' | 'heavy' },
  ) => {
    if (inflight.current.has(key)) return;
    inflight.current.add(key);
    setActionBusy(key);
    setErrorBanner(null);
    haptic(opts?.hapticIntent || 'tap');
    try {
      await fn();
      haptic('success');
      await load({ silent: true });
      opts?.onDone?.();
    } catch (e: any) {
      if (isNetworkError(e)) markOffline();
      setErrorBanner(humanizeError(e, 'default'));
      haptic('error');
    } finally {
      inflight.current.delete(key);
      setActionBusy(null);
    }
  }, [load, markOffline]);

  const openWhy = useCallback(async () => {
    if (!focus || !flags.explain) return;
    haptic('tap');
    setWhyOpen(true);
    if (!explanation) {
      const exp = await safe(() => api.getExplanation(focus.id));
      if (exp.status === 404) setFlags((f) => ({ ...f, explain: false }));
      else setExplanation(exp.data || null);
    }
  }, [focus, explanation, flags.explain]);

  const openHistory = useCallback(async () => {
    if (!focus) return;
    haptic('tap');
    setHistoryOpen(true);
    setHistory(null);
    const r = await safe(() => api.historyDecision(focus.id));
    if (r.status === 404 && String(r.error?.detail?.detail || r.error?.detail || '').includes('abilitato')) {
      setFlags((f) => ({ ...f, action: false }));
      setHistory([]);
    } else {
      setHistory(r.data?.items || []);
    }
  }, [focus]);

  const openOtherWhy = useCallback(async (id: string) => {
    haptic('tap');
    setOtherWhyLoading(id);
    const exp = await safe(() => api.getExplanation(id));
    setOtherWhyLoading(null);
    if (exp.data) setOtherWhy(exp.data);
  }, []);

  const onStart = () => focus && runAction(`start:${focus.id}`, () => api.startDecision(focus.id), { hapticIntent: 'tap' });
  const onComplete = () => focus && runAction(`complete:${focus.id}`, () => api.completeDecision(focus.id), {
    onDone: () => setConfirmCompleteOpen(false), hapticIntent: 'medium',
  });
  const onPartial = (pct: number, note?: string) =>
    focus && runAction(`partial:${focus.id}:${pct}`, () => api.partialDecision(focus.id, pct, undefined, note), {
      onDone: () => setPartialOpen(false), hapticIntent: 'medium',
    });
  const onPostpone = (until: string, reason?: string) =>
    focus && runAction(`postpone:${focus.id}`, () => api.postponeDecision(focus.id, until, reason), {
      onDone: () => setPostponeOpen(false), hapticIntent: 'medium',
    });
  const onBlock = (reason: string) =>
    focus && runAction(`block:${focus.id}`, () => api.blockDecision(focus.id, reason), {
      onDone: () => setBlockOpen(false), hapticIntent: 'medium',
    });
  const onDismiss = (reason?: string) =>
    focus && runAction(`dismiss:${focus.id}`, () => api.dismissDecision(focus.id, reason), {
      onDone: () => setDismissOpen(false), hapticIntent: 'tap',
    });

  const onRefresh = useCallback(async () => {
    haptic('select');
    setRefreshing(true);
    await load({ silent: true });
    setRefreshing(false);
  }, [load]);

  // Show calendar card only if the user has no instance yet (Hero A)
  // or has instance but never synced (Hero B). If synced (state C), we hide
  // the card from Home per spec §6: "sostituirlo con La tua giornata" — the DailyCard.
  const showCalendarCard = !instance || !instance.last_sync_at;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: tokens.color.surface }} edges={['top']} testID="home-safe">
      <ScrollView
        contentContainerStyle={{
          padding: tokens.spacing.lg,
          gap: tokens.spacing.lg,
          maxWidth: CONTAINER_MAX_WIDTH,
          width: '100%',
          alignSelf: 'center',
          paddingBottom: insets.bottom + 96,
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
        <HomeHeader online={online} lastSuccessAt={lastSuccessAt} />

        {!online ? <OfflineBanner /> : null}
        {errorBanner ? <ErrorBanner message={errorBanner} onDismiss={() => setErrorBanner(null)} /> : null}

        {loading ? (
          <FocusSkeleton />
        ) : focus ? (
          <Animated.View
            key={focus.id}
            entering={FadeInDown.duration(tokens.motion.slow)}
            exiting={FadeOut.duration(tokens.motion.fast)}
            layout={LinearTransition.duration(tokens.motion.base)}
          >
            <FocusNowCard
              decision={focus}
              explanation={explanation}
              explainEnabled={flags.explain}
              actionEnabled={flags.action}
              actionBusy={actionBusy}
              onWhy={openWhy}
              onStart={onStart}
              onComplete={() => { haptic('tap'); setConfirmCompleteOpen(true); }}
              onPartial={() => { haptic('tap'); setPartialOpen(true); }}
              onPostpone={() => { haptic('tap'); setPostponeOpen(true); }}
              onMore={() => { haptic('tap'); setMoreMenuOpen(true); }}
            />
          </Animated.View>
        ) : (
          <Animated.View entering={FadeInDown.duration(tokens.motion.slow)}>
            <EmptyFocus />
          </Animated.View>
        )}

        {loading ? (
          <DailySkeleton />
        ) : flags.daily && daily ? (
          <DailySummaryCard daily={daily} onOpen={() => { haptic('tap'); setDailyDetailOpen(true); }} />
        ) : null}

        {!loading && showCalendarCard ? (
          <CalendarConnectionCard
            instance={instance}
            eventsIngested={daily?.total_events}
            onAfterSync={() => load({ silent: true })}
            onAfterConnect={() => load({ silent: true })}
          />
        ) : null}

        <LaterList
          items={later}
          explainEnabled={flags.explain}
          onWhy={openOtherWhy}
          loadingWhyId={otherWhyLoading}
        />

        {loading && (
          <View style={{ gap: tokens.spacing.sm }}>
            <LaterSkeleton />
            <LaterSkeleton />
          </View>
        )}
      </ScrollView>

      {/* Modals */}
      <WhyNowSheet open={whyOpen} onClose={() => setWhyOpen(false)} explanation={explanation} />
      <DailyDetailSheet open={dailyDetailOpen} onClose={() => setDailyDetailOpen(false)} daily={daily} />
      <ConfirmSheet
        open={confirmCompleteOpen}
        onClose={() => setConfirmCompleteOpen(false)}
        title="Segnare come completata?"
        body="Verrà rimossa dal Focus Now."
        confirmLabel="Completa"
        onConfirm={onComplete}
        loading={actionBusy?.startsWith('complete:')}
      />
      <PartialSheet
        open={partialOpen}
        onClose={() => setPartialOpen(false)}
        onSubmit={onPartial}
        loading={actionBusy?.startsWith('partial:')}
      />
      <PostponeSheet
        open={postponeOpen}
        onClose={() => setPostponeOpen(false)}
        onSubmit={onPostpone}
        loading={actionBusy?.startsWith('postpone:')}
      />
      <ReasonSheet
        open={blockOpen}
        onClose={() => setBlockOpen(false)}
        title="Blocca la Decision"
        placeholder="Motivo del blocco (obbligatorio)"
        required
        onSubmit={onBlock}
        loading={actionBusy?.startsWith('block:')}
      />
      <ReasonSheet
        open={dismissOpen}
        onClose={() => setDismissOpen(false)}
        title="Ignora la Decision"
        placeholder="Motivo (opzionale)"
        onSubmit={onDismiss}
        loading={actionBusy?.startsWith('dismiss:')}
      />
      <MoreMenu
        open={moreMenuOpen}
        onClose={() => setMoreMenuOpen(false)}
        onBlock={() => { setMoreMenuOpen(false); setBlockOpen(true); }}
        onDismiss={() => { setMoreMenuOpen(false); setDismissOpen(true); }}
        onHistory={() => { setMoreMenuOpen(false); openHistory(); }}
      />
      <HistorySheet open={historyOpen} onClose={() => setHistoryOpen(false)} items={history} />
      <WhyNowSheet open={!!otherWhy} onClose={() => setOtherWhy(null)} explanation={otherWhy} />
    </SafeAreaView>
  );
}
