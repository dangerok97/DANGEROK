/**
 * ORA Home 3.0 — the ambient control surface of the user's life.
 *
 * Orchestration only: this file loads the payload, wires actions to the same
 * API contracts Home V2 used, and lays the sections out. Every ranking
 * decision still belongs to the backend, and no content is invented here —
 * a section with no real data does not render.
 *
 * Desktop is a two-column dashboard (decision column + contextual rail);
 * phone is the same hierarchy stacked. The two are one design, not a layout
 * and its compressed copy.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  RefreshControl,
  ScrollView,
  StyleSheet,
  View,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';

import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import {
  api, HomeActionDef, HomeItem, HomePriorityBand, HomeV2Response, ProactiveSuggestion,
} from '@/src/api/client';
import { useAuth } from '@/src/contexts/AuthContext';
import { triggerHaptic } from '@/src/theme/haptics';
import { useOnlineStatus, isNetworkError } from '@/src/hooks/use-online-status';
import { humanizeError } from '@/src/utils/errors';
import {
  OraInput,
  QuietGoogleNotice,
  OfflineBanner,
  ErrorBanner,
  PartialWarning,
  CorrectPriorityModal,
  SnoozeModal,
} from '@/src/components/home/quiet';
import {
  ContextRail,
  HeroAdesso,
  HomeEmptyV3,
  HomeHeaderV3,
  HomeSkeletonV3,
  HorizonSection,
  QuestionsSection,
  TodaySection,
  UpdatesFeed,
  allItems,
  splitSuggestions,
  todayItems,
} from '@/src/components/home/v3';
import { useAmbientInset } from '@/src/shell';

/**
 * Home is the one route allowed past PX1.1's 800px reading column: it is a
 * dashboard, not a document, and the reference composition needs two columns.
 * `PageContainer` is untouched — every other route keeps its measure.
 */
const DASHBOARD_MAX_WIDTH = 1320;
const MAIN_MIN_WIDTH = 560;
const RAIL_WIDTH = 340;
/** Below this the rail has nowhere to go and the page becomes one column. */
const TWO_COLUMN_MIN = 1100;

/**
 * Lays out one row of the dashboard.
 *
 * Two children → two columns. One child → the full width of the decision
 * column. Zero → nothing at all, including no gap. This is what keeps a
 * missing section from leaving a hole: the grid closes rather than reserving
 * space for content that does not exist.
 */
function SectionRow({
  twoColumn,
  children,
}: {
  twoColumn: boolean;
  children: React.ReactNode;
}) {
  const present = React.Children.toArray(children).filter(Boolean);
  if (!present.length) return null;
  if (!twoColumn || present.length === 1) {
    return <View style={styles.rowStacked}>{present}</View>;
  }
  return (
    <View style={styles.row}>
      {present.map((child, i) => (
        <View key={i} style={styles.rowCol}>{child}</View>
      ))}
    </View>
  );
}

export default function HomeScreen() {
  const router = useRouter();
  const { colors } = useTheme();
  const { user } = useAuth();
  const { width } = useWindowDimensions();
  const ambient = useAmbientInset();

  const twoColumn = width >= TWO_COLUMN_MIN;
  const wideHero = width >= 760;
  const padH = width < 380 ? tokens.spacing.lg : tokens.spacing.xl;

  const [home, setHome] = useState<HomeV2Response | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
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
      setErrorBanner(null);
    } catch (e: any) {
      if (isNetworkError(e)) markOffline();
      else setErrorBanner(humanizeError(e, 'default'));
    } finally {
      setLoading(false);
    }
  }, [markOffline, markOnline]);

  useEffect(() => { load(); }, [load]);
  // V2.9.4 can change Home in the background; re-reading on focus keeps a
  // suggestion appearing or disappearing from needing a full reload.
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
      void triggerHaptic('success');
      await load({ silent: true });
    } catch (e: any) {
      if (isNetworkError(e)) markOffline();
      setErrorBanner(humanizeError(e, 'default'));
      void triggerHaptic('error');
    } finally {
      inflight.current = false;
      setActionBusy(null);
    }
  }, [load, markOffline]);

  /**
   * Unchanged from Home V2 — the dual-step contract matters:
   * maps/navigate/study/confirm navigate only; open/guide/resume also record.
   */
  const onHeroAction = useCallback(async (action: HomeActionDef) => {
    const focus = home?.primary_focus;
    if (!focus) return;
    void triggerHaptic('impactLight');
    if (action.kind === 'snooze') { setPendingItemId(focus.id); setSnoozeOpen(true); return; }
    if (action.kind === 'correct') { setPendingItemId(focus.id); setCorrectOpen(true); return; }
    if (['maps', 'navigate', 'open', 'guide', 'study', 'resume', 'confirm'].includes(action.kind)) {
      if (action.kind === 'resume' || action.kind === 'open' || action.kind === 'guide') {
        await runHomeAction(focus.id, action.kind === 'resume' ? 'resume' : 'open');
      }
      if (action.route) router.push(action.route as any);
      return;
    }
    await runHomeAction(focus.id, action.kind === 'complete' ? 'complete' : action.kind);
  }, [home?.primary_focus, router, runHomeAction]);

  const onRefresh = useCallback(async () => {
    void triggerHaptic('selection');
    setRefreshing(true);
    try {
      const data = await api.refreshHome();
      setHome(data);
      markOnline();
    } catch (e: any) {
      if (isNetworkError(e)) markOffline();
      await load({ silent: true });
    } finally {
      setRefreshing(false);
    }
  }, [load, markOffline, markOnline]);

  const openItem = useCallback((item: HomeItem) => {
    void triggerHaptic('impactLight');
    const route = item.actions?.find((a) => a.route)?.route;
    if (route) router.push(route as any);
  }, [router]);

  const onSuggestionOpen = useCallback(async (s: ProactiveSuggestion) => {
    setSuggestionBusy(s.id);
    try {
      const res = await api.acceptSuggestion(s.id);
      void triggerHaptic('success');
      const r = (res.result || {}) as Record<string, unknown>;
      const route = (r.route as string | undefined)
        || ((r.result as any)?.route as string | undefined)
        || s.action?.route || undefined;
      await load({ silent: true });
      if (route) router.push(route as any);
    } catch (e: any) {
      if (isNetworkError(e)) markOffline();
      setErrorBanner(humanizeError(e, 'default'));
      void triggerHaptic('error');
    } finally {
      setSuggestionBusy(null);
    }
  }, [load, markOffline, router]);

  const onSuggestionDismiss = useCallback(async (id: string) => {
    setSuggestionBusy(id);
    try {
      await api.dismissSuggestion(id);
      void triggerHaptic('success');
      await load({ silent: true });
    } catch (e: any) {
      if (isNetworkError(e)) markOffline();
      setErrorBanner(humanizeError(e, 'default'));
    } finally {
      setSuggestionBusy(null);
    }
  }, [load, markOffline]);

  const focus = home?.primary_focus || null;
  const items = useMemo(() => allItems(home?.priorities), [home?.priorities]);
  const { questions, updates } = useMemo(
    () => splitSuggestions(home?.ora_ti_consiglia),
    [home?.ora_ti_consiglia],
  );
  /*
    Timeline views show everything that has a moment — including whatever is
    currently the hero. "Adesso" answers *what do I do*; "Oggi" and "Più
    avanti" answer *when is my life happening*. Dropping the most important
    upcoming thing out of the user's own timeline to avoid repeating it would
    make the timeline wrong to protect a tidiness nobody asked for.
  */
  const today = useMemo(() => todayItems(items), [items]);
  const horizon = useMemo(() => {
    const now = new Date().setHours(23, 59, 59, 999);
    return items
      .filter((i) => {
        const raw = i.start_at || i.due_at || i.goal_target_date;
        if (!raw) return false;
        const t = new Date(raw).getTime();
        return !Number.isNaN(t) && t > now;
      })
      .sort((a, b) => {
        const at = new Date(a.start_at || a.due_at || a.goal_target_date || 0).getTime();
        const bt = new Date(b.start_at || b.due_at || b.goal_target_date || 0).getTime();
        return at - bt;
      });
  }, [items]);

  const hasAnything = !!focus || questions.length > 0 || today.length > 0
    || updates.length > 0 || (home?.insights?.length ?? 0) > 0 || horizon.length > 0;

  const mainColumn = (
    <View style={styles.main}>
      {!online ? <OfflineBanner /> : null}
      {errorBanner ? (
        <ErrorBanner message={errorBanner} onDismiss={() => setErrorBanner(null)} />
      ) : null}
      {home?.partial ? <PartialWarning /> : null}

      {loading ? (
        <HomeSkeletonV3 wide={wideHero} />
      ) : focus ? (
        <HeroAdesso
          item={focus}
          explanation={home?.explanation}
          busy={actionBusy}
          wide={wideHero}
          onAction={onHeroAction}
          onSnooze={() => { setPendingItemId(focus.id); setSnoozeOpen(true); }}
          onCorrect={() => { setPendingItemId(focus.id); setCorrectOpen(true); }}
          onIgnore={() => runHomeAction(focus.id, 'ignore')}
        />
      ) : !hasAnything ? (
        <HomeEmptyV3 onAsk={() => router.push('/ora')} />
      ) : null}

      {!loading ? (
        <>
          {/*
            Sections pair up two-across when both halves exist and go full
            width when only one does. Laying them out as fixed halves left a
            column-wide hole whenever a section had no real data — and the
            answer to "no data" is to close the gap, never to fill it with
            something invented.
          */}
          <SectionRow twoColumn={twoColumn}>
            {questions.length ? (
              <QuestionsSection
                questions={questions}
                busyId={suggestionBusy}
                onAnswer={onSuggestionOpen}
              />
            ) : null}
            {today.length ? <TodaySection items={today} onOpen={openItem} /> : null}
          </SectionRow>

          <SectionRow twoColumn={twoColumn}>
            {updates.length || (home?.insights?.length ?? 0) ? (
              <UpdatesFeed
                suggestions={updates}
                insights={home?.insights || []}
                busyId={suggestionBusy}
                onOpen={onSuggestionOpen}
                onDismiss={onSuggestionDismiss}
                onInsight={(ins) => {
                  if (ins.action?.route) router.push(ins.action.route as any);
                  runHomeAction(ins.id, 'mark_insight_read');
                }}
              />
            ) : null}
            {horizon.length ? <HorizonSection items={horizon} onOpen={openItem} /> : null}
          </SectionRow>

          <QuietGoogleNotice
            visible={!!home?.google_calendar?.show_banner}
            onDismiss={() => runHomeAction('__google_banner__', 'dismiss_banner')}
            onConnected={() => load({ silent: true })}
          />

          {/* Quiet, never a giant ask box — the conversation lives in /ora. */}
          <OraInput onError={(msg) => setErrorBanner(msg)} />
        </>
      ) : null}
    </View>
  );

  return (
    <SafeAreaView
      edges={['top']}
      style={[styles.root, { backgroundColor: colors.backgroundPrimary }]}
      testID="home-safe"
    >
      <ScrollView
        contentContainerStyle={{
          paddingHorizontal: padH,
          paddingTop: tokens.spacing.lg,
          paddingBottom: ambient.paddingBottom,
          maxWidth: DASHBOARD_MAX_WIDTH,
          width: '100%',
          alignSelf: 'center',
          gap: tokens.spacing.xl,
        }}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={colors.textPrimary}
            colors={[colors.accent]}
            progressBackgroundColor={colors.surface}
          />
        }
        showsVerticalScrollIndicator={false}
        testID="home-scroll"
      >
        <HomeHeaderV3
          name={user?.name}
          onWhyNow={home?.explanation?.summary ? () => router.push('/situazione') : undefined}
        />

        {twoColumn ? (
          <View style={styles.columns}>
            <View style={styles.mainCol}>{mainColumn}</View>
            <View style={[styles.railCol, { width: RAIL_WIDTH }]}>
              {!loading ? (
                <ContextRail
                  items={items}
                  situation={home?.current_situation}
                  questionCount={questions.length}
                  onOpenItem={openItem}
                  onSeeAll={() => router.push('/situazione')}
                />
              ) : null}
            </View>
          </View>
        ) : (
          <>
            {mainColumn}
            {!loading ? (
              <ContextRail
                items={items}
                situation={home?.current_situation}
                questionCount={questions.length}
                onOpenItem={openItem}
                onSeeAll={() => router.push('/situazione')}
              />
            ) : null}
          </>
        )}
      </ScrollView>

      <CorrectPriorityModal
        open={correctOpen}
        onClose={() => setCorrectOpen(false)}
        current={
          (home?.primary_focus?.id === pendingItemId ? home?.primary_focus : null)?.priority
          ?? items.find((i) => i.id === pendingItemId)?.priority
          ?? null
        }
        onPick={(p) => {
          // The same correction contract Home V2 used: the ranking is the
          // backend's, so the choice is sent and the page reloads from what the
          // system decides — never patched locally to look correct.
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

const styles = StyleSheet.create({
  root: { flex: 1 },
  columns: { flexDirection: 'row', gap: tokens.spacing.xl, alignItems: 'flex-start' },
  mainCol: { flex: 1, minWidth: MAIN_MIN_WIDTH },
  railCol: { flexShrink: 0 },
  main: { gap: tokens.spacing.lg },
  row: { flexDirection: 'row', gap: tokens.spacing.lg, alignItems: 'flex-start' },
  /*
    Stacking is not just a direction change: `flex-start` top-aligns two cards
    in a row, but in a column it makes them hug their content instead of
    filling the width. Alignment has to flip with the axis.
  */
  rowStacked: { flexDirection: 'column', alignItems: 'stretch', gap: tokens.spacing.lg },
  rowCol: { flex: 1 },
});
