/**
 * Attività — the trust centre.
 *
 * Home says what matters most right now; this says what is going on between
 * the user and ORA overall: what ORA is asking, what it is holding until it
 * gets a yes, what cannot move yet, what changed, what is coming and what got
 * done. The structure is the point. Folding all of that into one feed would be
 * tidier and would destroy exactly the distinction a person needs in order to
 * trust the thing — being asked, being waited on, and being informed are not
 * the same event.
 *
 * Composition only. One aggregated read supplies every section, so the page
 * never fans out across half a dozen stores and the sections always agree with
 * each other. Nothing is ranked here, nothing is invented, and a section with
 * no real rows does not render.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';

import { api, type ActivityResponse } from '@/src/api/client';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { ErrorState } from '@/src/components/ui/ErrorState';
import { Appear, useAmbientInset } from '@/src/shell';
import { isNetworkError, useOnlineStatus } from '@/src/hooks/use-online-status';
import { humanizeError } from '@/src/utils/errors';
import { buildOraConversationHref } from '@/src/ora/oraNav';
import {
  ActivityEmpty,
  ActivityHeader,
  ActivitySkeleton,
  AttentionHero,
  CompletedPanel,
  DeadlinesPanel,
  QuestionsPanel,
  SummaryPanel,
  UpdatesPanel,
  WaitingPanel,
  WhyActivityDialog,
  isActivityEmpty,
} from '@/src/components/activity';

const PAGE_MAX_WIDTH = 1320;
const RAIL_WIDTH = 300;
/** Below this the rail has nowhere to sit and the page becomes one column. */
const TWO_COLUMN_MIN = 1100;
/** Below this the two mid panels stop sharing a row. */
const PAIR_MIN = 760;

export default function AttivitaScreen() {
  const { colors } = useTheme();
  const ambient = useAmbientInset();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const { markOffline, markOnline } = useOnlineStatus();

  const twoColumn = width >= TWO_COLUMN_MIN;
  const pair = width >= PAIR_MIN;
  const padH = width < 380 ? tokens.spacing.lg : tokens.spacing.xl;

  const [activity, setActivity] = useState<ActivityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [whyOpen, setWhyOpen] = useState(false);

  const load = useCallback(
    async (opts?: { silent?: boolean }) => {
      if (!opts?.silent) setLoading(true);
      try {
        const res = await api.getActivity();
        markOnline();
        setActivity(res);
        setError(null);
      } catch (e: any) {
        if (isNetworkError(e)) markOffline();
        setError(humanizeError(e, 'default'));
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [markOffline, markOnline],
  );

  useEffect(() => {
    void load();
  }, [load]);

  useFocusEffect(
    useCallback(() => {
      void load({ silent: true });
    }, [load]),
  );

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    void load({ silent: true });
  }, [load]);

  const open = useCallback(
    (route?: string | null) => {
      if (route) router.push(route as any);
    },
    [router],
  );

  /**
   * Answering goes to the exact place the answer belongs.
   *
   * A clarification opens the memory loop that owns it; a suggestion opens the
   * route it already carries. Only when neither exists does the conversation
   * take over, and even then it is a real destination rather than a shrug.
   * Nothing here executes the proposed action: a consent request is answered
   * by the user in the flow that owns it, never by this page on their behalf.
   */
  const answer = useCallback(
    async (q: ActivityResponse['questions'][number]) => {
      if (q.kind === 'memory_clarification' && q.memory_id) {
        try {
          const res = await api.lifeMemoryClarifyStart(q.memory_id);
          if (res?.route) router.push(res.route as any);
          else if (res?.session?.id) router.push(`/memory-clarify/${res.session.id}` as any);
        } catch (e: any) {
          setError(humanizeError(e, 'default'));
        }
        return;
      }
      if (q.route) {
        router.push(q.route as any);
        return;
      }
      router.push(buildOraConversationHref({ entryPoint: 'home' }) as any);
    },
    [router],
  );

  const act = useCallback(
    (action: { kind: string; route?: string | null }) => {
      if (action.route) router.push(action.route as any);
    },
    [router],
  );

  const empty = useMemo(() => isActivityEmpty(activity), [activity]);

  const main = activity ? (
    <>
      {activity.attention ? <AttentionHero attention={activity.attention} onAct={act} /> : null}
      <View style={pair ? styles.pairRow : styles.stack}>
        <View style={pair ? styles.pairCell : undefined}>
          <QuestionsPanel questions={activity.questions} onAnswer={(q) => void answer(q)} />
        </View>
        <View style={pair ? styles.pairCell : undefined}>
          <WaitingPanel waiting={activity.waiting} onOpen={open} />
        </View>
      </View>
      <UpdatesPanel updates={activity.updates} onOpen={open} />
    </>
  ) : null;

  const rail = activity ? (
    <>
      <SummaryPanel rows={activity.summary} />
      <DeadlinesPanel deadlines={activity.deadlines} onOpen={open} />
      <CompletedPanel completed={activity.completed} />
    </>
  ) : null;

  return (
    <SafeAreaView
      edges={['top']}
      style={[styles.root, { backgroundColor: colors.backgroundPrimary }]}
      testID="attivita-screen"
    >
      <ScrollView
        contentContainerStyle={{
          paddingHorizontal: padH,
          paddingTop: tokens.spacing.lg,
          paddingBottom: ambient.paddingBottom + tokens.spacing.xxl,
          maxWidth: PAGE_MAX_WIDTH,
          width: '100%',
          alignSelf: 'center',
          gap: tokens.spacing.xl,
        }}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={colors.textTertiary}
          />
        }
        showsVerticalScrollIndicator={false}
        testID="activity-scroll"
      >
        {loading && !activity ? (
          <ActivitySkeleton wide={twoColumn} />
        ) : (
          <>
            <ActivityHeader onWhy={() => setWhyOpen(true)} />

            {error && !activity ? (
              <ErrorState
                title="Non riesco a caricare Attività"
                message={error}
                onRetry={() => void load()}
              />
            ) : empty ? (
              <ActivityEmpty />
            ) : (
              <>
                {activity?.partial ? (
                  <Text
                    style={[styles.partial, { color: colors.textTertiary }]}
                    testID="activity-partial"
                  >
                    Alcune informazioni non sono disponibili al momento.
                  </Text>
                ) : null}

                {/*
                  Content arriving where the skeleton stood: a 200ms fade, no
                  movement, skipped entirely under reduce-motion. The skeleton
                  already holds the real layout, so anything that slid would be
                  describing a displacement that never happened.
                */}
                <Appear>
                  {twoColumn ? (
                    <View style={styles.row}>
                      <View style={styles.mainCol}>{main}</View>
                      <View style={[styles.railCol, { width: RAIL_WIDTH }]}>{rail}</View>
                    </View>
                  ) : (
                    // Phone: the same order, stacked. The rail's panels become
                    // ordinary sections rather than being dropped.
                    <View style={styles.stackAll}>
                      {main}
                      {rail}
                    </View>
                  )}
                </Appear>
              </>
            )}
          </>
        )}
      </ScrollView>

      <WhyActivityDialog open={whyOpen} onClose={() => setWhyOpen(false)} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  row: { flexDirection: 'row', gap: tokens.spacing.xl, alignItems: 'flex-start' },
  mainCol: { flex: 1, minWidth: 0, gap: tokens.spacing.lg },
  railCol: { gap: tokens.spacing.lg },
  stackAll: { gap: tokens.spacing.lg },
  pairRow: { flexDirection: 'row', gap: tokens.spacing.lg, alignItems: 'flex-start' },
  pairCell: { flex: 1, minWidth: 0 },
  stack: { gap: tokens.spacing.lg },
  partial: {
    fontSize: tokens.typography.caption.fontSize,
    lineHeight: tokens.typography.caption.lineHeight,
  },
});
