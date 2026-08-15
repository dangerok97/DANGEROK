/**
 * Goal Workspace — Quiet Premium, domain-neutral Life OS + GenerativeObjects.
 * Presentation only — plan/object semantics unchanged.
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { api } from '@/src/api/client';
import { GenerativeObjectRenderer } from '@/src/components/generative/GenerativeObjectRenderer';
import { AppCard } from '@/src/components/ui/AppCard';
import { AppScreen } from '@/src/components/ui/AppScreen';
import { ScreenHeader } from '@/src/components/ui/ScreenHeader';
import { SectionHeader } from '@/src/components/ui/SectionHeader';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { humanizeError } from '@/src/utils/errors';
import { buildOraConversationHref } from '@/src/ora/oraNav';

export default function GoalWorkspaceScreen() {
  const { planId } = useLocalSearchParams<{ planId: string }>();
  const router = useRouter();
  const { colors } = useTheme();
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
  const objects = bundle?.objects || [];
  const sess = plan?.conversation_session_id as string | undefined;
  const activeObjectId = focusedObjectId || (objects[0]?.id as string | undefined);
  const nextItemId = bundle?.next_item?.id as string | undefined;

  const continueWithOra = useCallback(async () => {
    if (!sess) {
      // No linked session yet — open fresh ORA with plan focus when message starts
      router.push(
        buildOraConversationHref({
          planId: String(planId),
          objectId: activeObjectId,
          planItemId: nextItemId,
          entryPoint: 'goal_workspace',
        }) as any,
      );
      return;
    }
    try {
      await api.lifeOsSessionFocus({
        session_id: String(sess),
        object_id: activeObjectId,
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
        objectId: activeObjectId,
        planItemId: nextItemId,
        entryPoint: 'goal_workspace',
      }) as any,
    );
  }, [sess, activeObjectId, planId, nextItemId, router]);

  const askOraAboutObject = useCallback(
    async (objectId: string) => {
      setFocusedObjectId(objectId);
      if (!sess) {
        router.push(
          buildOraConversationHref({
            planId: String(planId),
            objectId,
            planItemId: nextItemId,
            entryPoint: 'object',
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
          entryPoint: 'object',
        }) as any,
      );
    },
    [sess, planId, nextItemId, router],
  );

  if (loading) {
    return (
      <AppScreen testID="goal-workspace-loading">
        <ActivityIndicator color={colors.textPrimary} />
      </AppScreen>
    );
  }

  if (error || !plan) {
    return (
      <AppScreen testID="goal-workspace-error">
        <ScreenHeader title="Workspace" onBack={() => router.back()} />
        <Text style={{ color: colors.textSecondary }}>{error || 'Piano non trovato'}</Text>
        <Pressable onPress={() => router.back()} style={{ marginTop: tokens.spacing.md }}>
          <Text style={{ color: colors.textPrimary, textDecorationLine: 'underline' }}>
            Indietro
          </Text>
        </Pressable>
      </AppScreen>
    );
  }

  const progressPct = Math.round((bundle.progress_ratio || 0) * 100);

  return (
    <AppScreen scroll testID="goal-workspace" contentStyle={styles.content}>
      <ScreenHeader
        eyebrow="Workspace"
        title={plan.summary || 'Il tuo obiettivo'}
        subtitle={plan.desired_outcome || undefined}
        onBack={() => router.back()}
      />

      <View style={styles.metaRow}>
        {plan.target_date ? (
          <Text style={[styles.meta, { color: colors.textTertiary }]}>
            Orizzonte {plan.target_date}
          </Text>
        ) : null}
        <Text style={[styles.meta, { color: colors.textTertiary }]}>
          Progresso {progressPct}%
        </Text>
      </View>

      {bundle.next_item ? (
        <AppCard style={styles.block}>
          <Text style={[styles.cardLabel, { color: colors.textTertiary }]}>Prossimo passo</Text>
          <Text style={[styles.body, { color: colors.textPrimary }]}>
            {bundle.next_item.title}
          </Text>
        </AppCard>
      ) : null}

      <SectionHeader title="Piano" subtitle="Progressione" />
      <View style={styles.planList}>
        {(plan.items || []).map((it: any) => (
          <Text key={it.id} style={[styles.body, { color: colors.textPrimary }]}>
            {it.status === 'completed' ? '✓' : '·'} {it.title}
            {it.due_date ? `  (${it.due_date})` : ''}
          </Text>
        ))}
        {!plan.items?.length ? (
          <Text style={{ color: colors.textSecondary }}>Nessun passo ancora.</Text>
        ) : null}
      </View>

      <SectionHeader title="Il tuo lavoro" subtitle="Oggetti creati con ORA" />
      {!objects.length ? (
        <Text style={{ color: colors.textSecondary, marginBottom: tokens.spacing.lg }}>
          Nessun oggetto ancora — continua con ORA per crearne.
        </Text>
      ) : (
        objects.map((obj: any) => (
          <AppCard key={obj.id} style={styles.block} elevated={obj.id === activeObjectId}>
            <Text style={[styles.cardTitle, { color: colors.textPrimary }]}>{obj.title}</Text>
            {obj.purpose ? (
              <Text style={{ color: colors.textSecondary, marginBottom: 8 }}>{obj.purpose}</Text>
            ) : null}
            {obj.revision != null ? (
              <Text style={[styles.meta, { color: colors.textTertiary }]}>rev {obj.revision}</Text>
            ) : null}
            <GenerativeObjectRenderer
              content={obj.content}
              objectId={obj.id}
              onInteract={async (eventType, payload) => {
                setFocusedObjectId(obj.id);
                try {
                  await api.lifeOsObjectInteract(obj.id, {
                    event_type: eventType,
                    payload,
                  });
                  if (sess) {
                    await api.lifeOsSessionFocus({
                      session_id: String(sess),
                      object_id: obj.id,
                      plan_id: String(planId),
                      plan_item_id: nextItemId,
                      event_type: eventType || 'object_opened',
                    });
                  }
                } catch {
                  /* soft */
                }
              }}
            />
            <Pressable
              onPress={() => void askOraAboutObject(obj.id)}
              style={[styles.objectCta, { borderColor: colors.border }]}
              testID={`ask-ora-object-${obj.id}`}
            >
              <Text style={{ color: colors.textPrimary, fontWeight: '600' }}>
                Continua con ORA
              </Text>
            </Pressable>
          </AppCard>
        ))
      )}

      {(() => {
        const fromApi = (bundle?.public_sources || []) as Array<{
          display_name?: string;
          authority_label?: string;
          uploaded_by_user?: boolean;
        }>;
        const sources =
          fromApi.length > 0
            ? fromApi
                .map((s) => ({
                  name: String(s.display_name || '').trim(),
                  authority: String(s.authority_label || '').trim(),
                }))
                .filter((s) => s.name && !/^(lcf_|doc_|lop_|lgo_)/i.test(s.name))
            : [];
        if (!sources.length) return null;
        return (
          <View style={{ marginBottom: tokens.spacing.xl }} testID="goal-workspace-fonti">
            <SectionHeader title="Fonti" subtitle="Prove fornite" />
            {sources.slice(0, 8).map((s) => (
              <View
                key={s.name}
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: 8,
                  marginBottom: 8,
                }}
              >
                <Text style={{ color: colors.textSecondary }}>·</Text>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: colors.textPrimary }}>{s.name}</Text>
                  {s.authority ? (
                    <Text style={{ color: colors.textTertiary || colors.textSecondary, fontSize: 12 }}>
                      {s.authority}
                    </Text>
                  ) : null}
                </View>
              </View>
            ))}
          </View>
        );
      })()}

      <View style={styles.actions}>
        <Pressable
          onPress={() => void continueWithOra()}
          style={[styles.btnPrimary, { backgroundColor: colors.textPrimary }]}
          testID="goal-workspace-continue-ora"
        >
          <Text style={[styles.btnPrimaryText, { color: colors.backgroundPrimary }]}>
            Continua con ORA
          </Text>
        </Pressable>
        <Pressable
          onPress={load}
          style={[styles.btnSecondary, { borderColor: colors.border }]}
          testID="goal-workspace-refresh"
        >
          <Text style={{ color: colors.textPrimary }}>Aggiorna</Text>
        </Pressable>
      </View>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  content: { paddingBottom: 48 },
  metaRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: tokens.spacing.lg },
  meta: { fontSize: 13 },
  block: { marginBottom: tokens.spacing.lg, gap: tokens.spacing.sm },
  cardLabel: {
    fontSize: 12,
    fontWeight: '600',
    letterSpacing: 0.6,
    textTransform: 'uppercase',
  },
  cardTitle: { fontSize: 17, fontWeight: '600' },
  body: { fontSize: 15, lineHeight: 22 },
  planList: { gap: 8, marginBottom: tokens.spacing.xl },
  objectCta: {
    marginTop: tokens.spacing.md,
    paddingVertical: 12,
    alignItems: 'center',
    borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth,
  },
  actions: { marginTop: tokens.spacing.md, gap: tokens.spacing.sm },
  btnPrimary: {
    paddingVertical: 14,
    alignItems: 'center',
    borderRadius: 12,
  },
  btnPrimaryText: { fontSize: 16, fontWeight: '600' },
  btnSecondary: {
    paddingVertical: 14,
    alignItems: 'center',
    borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth,
  },
});
