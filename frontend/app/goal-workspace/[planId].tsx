/**
 * ORA Workspace 2.0 — where the user and ORA actually work on a goal.
 *
 * Home is what needs attention; the Workspace is where it gets advanced. So
 * this page answers six questions in order and nothing else: what am I working
 * on, where have I got to, what must I do now, what has ORA prepared, what
 * comes next, and how do I keep going with ORA.
 *
 * Orchestration only. Plan semantics, object semantics, focus events and the
 * conversation hand-off are exactly the ones that already existed — the same
 * API calls, the same context identifiers. What changed is the hierarchy: the
 * generative object ORA produced is now the centre of the page rather than one
 * card in a stack, and the plan has moved beside it as context.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Pressable } from 'react-native';

import { api } from '@/src/api/client';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { humanizeError } from '@/src/utils/errors';
import { buildOraConversationHref } from '@/src/ora/oraNav';
import { useAmbientInset } from '@/src/shell';
import {
  ActiveWork,
  CurrentStep,
  MaterialSelector,
  NoWorkYet,
  PlanComplete,
  PlanProgress,
  WorkspaceError,
  WorkspaceHeader,
  WorkspaceSkeleton,
  WorkspaceSources,
  humanDate,
  isPlanComplete,
  materials as materialsOf,
  planProgression,
  publicSources,
} from '@/src/components/workspace';

const WORKSPACE_MAX_WIDTH = 1180;
/** The rail is context, never a second column of work. */
const RAIL_WIDTH = 300;
/** Below this the rail has nowhere to sit and the page becomes one column. */
const TWO_COLUMN_MIN = 1040;

export default function GoalWorkspaceScreen() {
  const { planId } = useLocalSearchParams<{ planId: string }>();
  const router = useRouter();
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const ambient = useAmbientInset();

  const twoColumn = width >= TWO_COLUMN_MIN;
  const padH = width < 380 ? tokens.spacing.lg : tokens.spacing.xl;

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [bundle, setBundle] = useState<any>(null);
  const [focusedObjectId, setFocusedObjectId] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!planId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.getLifeOsPlan(String(planId));
      setBundle(res);
      const objs = res?.objects || [];
      if (objs[0]?.id) setFocusedObjectId((prev) => prev || objs[0].id);
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
    } finally {
      setLoading(false);
    }
  }, [planId]);

  useEffect(() => {
    load();
  }, [load]);

  const plan = bundle?.plan;
  const objects = (bundle?.objects || []) as any[];
  const sess = plan?.conversation_session_id as string | undefined;
  const activeObjectId = focusedObjectId || (objects[0]?.id as string | undefined);
  const nextItemId = bundle?.next_item?.id as string | undefined;
  const activeObject = objects.find((o) => o?.id === activeObjectId) || objects[0] || null;

  const goBack = useCallback(() => router.back(), [router]);

  /**
   * The hand-off to ORA. Unchanged: focus is recorded first when a session
   * exists, and every context identifier the conversation needs to know what
   * we were doing travels with the route.
   */
  const openOra = useCallback(
    async (objectId: string | undefined, entryPoint: 'goal_workspace' | 'object') => {
      if (!sess) {
        router.push(
          buildOraConversationHref({
            planId: String(planId),
            objectId,
            planItemId: nextItemId,
            entryPoint,
          }) as any,
        );
        return;
      }
      try {
        await api.lifeOsSessionFocus({
          session_id: String(sess),
          object_id: objectId,
          plan_id: String(planId),
          plan_item_id: nextItemId,
          event_type: 'object_opened',
        });
      } catch {
        /* soft */
      }
      router.push(
        buildOraConversationHref({
          sessionId: sess,
          planId: String(planId),
          objectId,
          planItemId: nextItemId,
          entryPoint,
        }) as any,
      );
    },
    [sess, planId, nextItemId, router],
  );

  const continueWithOra = useCallback(
    () => openOra(activeObjectId, 'goal_workspace'),
    [openOra, activeObjectId],
  );

  const askOraAboutObject = useCallback(
    (objectId: string) => {
      setFocusedObjectId(objectId);
      return openOra(objectId, 'object');
    },
    [openOra],
  );

  const onInteract = useCallback(
    async (objectId: string, eventType: string, payload: Record<string, unknown>) => {
      setFocusedObjectId(objectId);
      try {
        await api.lifeOsObjectInteract(objectId, { event_type: eventType, payload });
        if (sess) {
          await api.lifeOsSessionFocus({
            session_id: String(sess),
            object_id: objectId,
            plan_id: String(planId),
            plan_item_id: nextItemId,
            event_type: eventType || 'object_opened',
          });
        }
      } catch {
        /* soft */
      }
    },
    [sess, planId, nextItemId],
  );

  const steps = useMemo(
    () => planProgression(plan?.items, nextItemId),
    [plan?.items, nextItemId],
  );
  const sources = useMemo(() => publicSources(bundle?.public_sources), [bundle?.public_sources]);
  const materials = useMemo(() => materialsOf(objects), [objects]);
  const complete = isPlanComplete(plan, bundle?.next_item);

  const frame = (children: React.ReactNode, testID: string) => (
    <SafeAreaView
      edges={['top']}
      style={[styles.root, { backgroundColor: colors.backgroundPrimary }]}
      testID={testID}
    >
      <ScrollView
        contentContainerStyle={{
          paddingHorizontal: padH,
          paddingTop: tokens.spacing.lg,
          paddingBottom: ambient.paddingBottom,
          maxWidth: WORKSPACE_MAX_WIDTH,
          width: '100%',
          alignSelf: 'center',
          gap: tokens.spacing.xl,
        }}
        showsVerticalScrollIndicator={false}
        testID="workspace-scroll"
      >
        {children}
      </ScrollView>
    </SafeAreaView>
  );

  if (loading) return frame(<WorkspaceSkeleton wide={twoColumn} />, 'goal-workspace-loading');

  if (error || !plan) {
    return frame(
      <>
        <WorkspaceHeader onBack={goBack} />
        <WorkspaceError message={error} onRetry={load} onBack={goBack} />
      </>,
      'goal-workspace-error',
    );
  }

  /* ---- the three blocks of the main column ---- */

  const currentStep = complete ? (
    <PlanComplete onBack={goBack} />
  ) : bundle?.next_item ? (
    <CurrentStep
      title={bundle.next_item.title}
      detail={bundle.next_item.description || null}
      // The only action a Workspace can honestly offer for any goal is to keep
      // going with ORA. Anything more specific would have to be guessed from
      // the domain, and this page does not know domains.
      ctaLabel="Continua con ORA"
      onPress={() => void continueWithOra()}
    />
  ) : (
    <CurrentStep
      title="Continua da dove eravate rimasti."
      detail="ORA riprende il filo di questo obiettivo con te."
      ctaLabel="Continua con ORA"
      onPress={() => void continueWithOra()}
    />
  );

  // A finished goal with nothing left behind says so once, in the completion
  // block. Telling the user that material "will appear here" would promise
  // work on something that is already over.
  const workSurface = !activeObject && complete ? null : activeObject ? (
    <ActiveWork
      title={activeObject.title || 'Il tuo lavoro'}
      purpose={activeObject.purpose || null}
      content={activeObject.content}
      objectId={String(activeObject.id)}
      onInteract={(eventType, payload) =>
        void onInteract(String(activeObject.id), eventType, payload)
      }
      onAskOra={() => void askOraAboutObject(String(activeObject.id))}
    />
  ) : (
    <NoWorkYet />
  );

  const context = (
    <>
      <PlanProgress steps={steps} />
      <WorkspaceSources sources={sources} />
      <Pressable
        onPress={load}
        style={({ pressed }) => [styles.refresh, { borderColor: colors.border }, pressed && styles.pressed]}
        accessibilityRole="button"
        testID="goal-workspace-refresh"
      >
        <Ionicons name="refresh" size={14} color={colors.textTertiary} />
        <Text style={[styles.refreshLabel, { color: colors.textSecondary }]}>Aggiorna</Text>
      </Pressable>
    </>
  );

  return frame(
    <>
      <WorkspaceHeader
        title={plan.summary || 'Il tuo obiettivo'}
        outcome={plan.desired_outcome || null}
        horizon={humanDate(plan.target_date)}
        onBack={goBack}
      />

      {twoColumn ? (
        <View style={styles.row}>
          <View style={styles.mainCol}>
            {currentStep}
            <MaterialSelector
              materials={materials}
              activeId={activeObjectId}
              onSelect={setFocusedObjectId}
            />
            {workSurface}
          </View>
          <View style={[styles.railCol, { width: RAIL_WIDTH }]}>{context}</View>
        </View>
      ) : (
        // Phone: the same hierarchy stacked. Work first, context after it —
        // the rail's content is what you consult, not what you act on.
        <View style={styles.stack}>
          {currentStep}
          <MaterialSelector
            materials={materials}
            activeId={activeObjectId}
            onSelect={setFocusedObjectId}
          />
          {workSurface}
          {context}
        </View>
      )}
    </>,
    'goal-workspace',
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  row: { flexDirection: 'row', gap: tokens.spacing.xl, alignItems: 'flex-start' },
  /** Main work area: takes the room the rail does not, ~700–820px in practice. */
  mainCol: { flex: 1, minWidth: 0, gap: tokens.spacing.lg },
  railCol: { gap: tokens.spacing.lg },
  stack: { gap: tokens.spacing.lg },
  refresh: {
    flexDirection: 'row', alignItems: 'center', gap: 7, alignSelf: 'flex-start',
    minHeight: tokens.touch.min, paddingHorizontal: tokens.spacing.lg,
    borderRadius: tokens.radius.md, borderWidth: StyleSheet.hairlineWidth,
  },
  refreshLabel: { fontSize: 13 },
  pressed: { opacity: 0.7 },
});
