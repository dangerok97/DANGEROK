/**
 * ORA Home Quiet Premium — orchestration only.
 * Presentation/UX; no ranking/API/engine changes.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  View,
  ScrollView,
  RefreshControl,
  StyleSheet,
  useWindowDimensions,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';

import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { AppScreen } from '@/src/components/ui/AppScreen';
import {
  api, HomeV2Response, HomeActionDef, HomePriorityBand,
} from '@/src/api/client';
import { triggerHaptic } from '@/src/theme/haptics';
import { useOnlineStatus, isNetworkError } from '@/src/hooks/use-online-status';
import { humanizeError } from '@/src/utils/errors';
import {
  HomeAmbientHeader,
  OraInput,
  DailyFocus,
  FocusHorizon,
  PrioritySection,
  UpdatesSection,
  SituationSummary,
  ContinueSection,
  HomeLoading,
  QuietGoogleNotice,
  OfflineBanner,
  ErrorBanner,
  PartialWarning,
  CorrectPriorityModal,
  SnoozeModal,
} from '@/src/components/home/quiet';
import { EmptyHome } from '@/src/components/home/v2/EmptyHome';

/** Editorial column — generous but not dashboard-wide */
const HOME_MAX_WIDTH = 860;

export default function HomeScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const padH = width < 360 ? tokens.spacing.lg : tokens.spacing.xl; // 16 / 24
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

  const onDynamicAction = useCallback(async (action: HomeActionDef) => {
    const focus = home?.primary_focus;
    if (!focus) return;
    void triggerHaptic('impactLight');
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
      if (action.kind === 'resume' || action.kind === 'open' || action.kind === 'guide') {
        await runHomeAction(focus.id, action.kind === 'resume' ? 'resume' : 'open');
      }
      return;
    }
    await runHomeAction(focus.id, action.kind === 'complete' ? 'complete' : action.kind);
  }, [home?.primary_focus, runHomeAction]);

  const onRefresh = useCallback(async () => {
    void triggerHaptic('selection');
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
    <AppScreen
      padded={false}
      edges={['top']}
      testID="home-safe"
      style={{ backgroundColor: colors.backgroundPrimary }}
    >
      <ScrollView
        contentContainerStyle={{
          paddingHorizontal: padH,
          paddingTop: tokens.spacing.lg,
          gap: tokens.spacing['32'],
          maxWidth: HOME_MAX_WIDTH,
          width: '100%',
          alignSelf: 'center',
          paddingBottom: Math.max(insets.bottom, 16) + 108,
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
        <HomeAmbientHeader online={online} lastSuccessAt={lastSuccessAt} />
        {!online ? <OfflineBanner /> : null}
        {errorBanner ? (
          <ErrorBanner message={errorBanner} onDismiss={() => setErrorBanner(null)} />
        ) : null}
        {home?.partial ? <PartialWarning /> : null}

        {loading ? (
          <HomeLoading />
        ) : focus ? (
          <View style={styles.focusBlock}>
            <DailyFocus
              item={focus}
              explanation={home?.explanation}
              busy={actionBusy}
              onAction={onDynamicAction}
              onCorrect={() => { setPendingItemId(focus.id); setCorrectOpen(true); }}
              onIgnore={() => runHomeAction(focus.id, 'ignore')}
            />
          </View>
        ) : (
          <EmptyHome />
        )}

        {/* Ask bar — after Daily Focus so it is not the first hero module */}
        <OraInput onError={(msg) => setErrorBanner(msg)} />

        {!loading ? <FocusHorizon home={home} /> : null}

        {!loading && home?.priorities ? <PrioritySection groups={home.priorities} /> : null}

        {!loading && home?.current_situation ? (
          <SituationSummary
            situation={home.current_situation}
            onOpen={() => {
              void triggerHaptic('impactLight');
              router.push('/situazione');
            }}
          />
        ) : null}

        {!loading ? (
          <QuietGoogleNotice
            visible={showGoogleBanner}
            onDismiss={() => runHomeAction('__google_banner__', 'dismiss_banner')}
            onConnected={() => load({ silent: true })}
          />
        ) : null}

        {!loading ? (
          <UpdatesSection
            suggestions={home?.ora_ti_consiglia}
            insights={home?.insights}
            busyId={suggestionBusy}
            onAccept={async (id) => {
              setSuggestionBusy(id);
              try {
                const res = await api.acceptSuggestion(id);
                void triggerHaptic('success');
                const r = (res.result || {}) as Record<string, unknown>;
                const route =
                  (r.route as string | undefined) ||
                  ((r.result as any)?.route as string | undefined);
                await load({ silent: true });
                if (route) router.push(route as any);
              } catch (e: any) {
                if (isNetworkError(e)) markOffline();
                setErrorBanner(humanizeError(e, 'default'));
                void triggerHaptic('error');
              } finally {
                setSuggestionBusy(null);
              }
            }}
            onDismiss={async (id) => {
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
            }}
            onSnooze={async (id, preset) => {
              setSuggestionBusy(id);
              try {
                await api.snoozeSuggestion(id, { preset });
                void triggerHaptic('success');
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
            onIgnoreInsight={(id) => runHomeAction(id, 'ignore')}
            onInsightAction={(ins) => {
              if (ins.action?.route) router.push(ins.action.route as any);
              runHomeAction(ins.id, 'mark_insight_read');
            }}
          />
        ) : null}

        {!loading && home?.resume_item ? (
          <ContinueSection
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
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  focusBlock: { gap: tokens.spacing.md },
});
