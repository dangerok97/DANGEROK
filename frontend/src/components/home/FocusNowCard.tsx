import { View, Text, StyleSheet, Pressable } from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';
import { Ionicons } from '@expo/vector-icons';
import { tokens } from '@/src/theme/tokens';
import { ApiDecision, DecisionExplanation } from '@/src/api/client';
import {
  CONFIDENCE_LABELS, IMPACT_LABELS, RISK_LABELS, STATUS_LABELS, formatMinutes, formatDateTime,
} from '@/src/utils/labels';
import { ActionBtn } from '@/src/components/ui/ActionBtn';

type Props = {
  decision: ApiDecision;
  explanation: DecisionExplanation | null;
  explainEnabled: boolean;
  actionEnabled: boolean;
  actionBusy: string | null;
  onWhy: () => void;
  onStart: () => void;
  onComplete: () => void;
  onPartial: () => void;
  onPostpone: () => void;
  onMore: () => void;
};

export function FocusNowCard({
  decision, explanation, explainEnabled, actionEnabled, actionBusy,
  onWhy, onStart, onComplete, onPartial, onPostpone, onMore,
}: Props) {
  const risk = explanation?.estimated_postpone_risk;
  const impact = explanation?.estimated_impact;
  const conf = explanation?.confidence;
  const st = decision.action_state?.status || decision.status;
  const pct = decision.action_state?.completion_percentage as number | null | undefined;
  const inProgress = st === 'in_progress';
  const partial = st === 'partially_completed';
  const statusColor = inProgress ? tokens.color.info : partial ? tokens.color.warning : tokens.color.onSurfaceMuted;

  return (
    <View style={styles.card} testID="focus-card">
      <View style={styles.header}>
        <View style={styles.pill} accessibilityLabel="Focus adesso">
          <View style={styles.pillDot} />
          <Text style={styles.pillText}>ORA</Text>
        </View>
        <View
          style={[styles.statusPill, { borderColor: statusColor }]}
          accessibilityLabel={`Stato ${STATUS_LABELS[st] || 'Da fare'}`}
        >
          <View style={[styles.dot, { backgroundColor: statusColor }]} />
          <Text style={styles.statusText}>{STATUS_LABELS[st] || 'Da fare'}</Text>
        </View>
      </View>

      <Text style={styles.title} accessibilityRole="header">{decision.title}</Text>
      {decision.description ? <Text style={styles.desc}>{decision.description}</Text> : null}

      {inProgress ? (
        <View style={styles.progressWrap} accessibilityLabel="In corso">
          <View style={styles.progressTrack}>
            <Animated.View
              entering={FadeIn.duration(tokens.motion.base)}
              style={[
                styles.progressBar,
                { width: `${Math.max(10, (pct as number) || 20)}%`, backgroundColor: tokens.color.info },
              ]}
            />
          </View>
          <Text style={styles.progressLabel}>{pct != null ? `Avanzamento ${pct}%` : 'In corso'}</Text>
        </View>
      ) : partial && pct != null ? (
        <View style={styles.progressWrap} accessibilityLabel={`Completata ${pct}%`}>
          <View style={styles.progressTrack}>
            <View style={[styles.progressBar, { width: `${pct}%`, backgroundColor: tokens.color.warning }]} />
          </View>
          <Text style={styles.progressLabel}>Parziale · {pct}%</Text>
        </View>
      ) : null}

      {explanation?.human_summary ? (
        <View style={styles.summaryBox}>
          <Ionicons name="sparkles-outline" size={13} color={tokens.color.onSurfaceMuted} />
          <Text style={styles.summary}>{explanation.human_summary}</Text>
        </View>
      ) : null}

      <View style={styles.metaGrid}>
        <MetaItem icon="time-outline" label="Durata" value={formatMinutes(decision.time_required_min)} />
        <MetaItem
          icon="flag-outline" label="Impatto"
          value={impact ? IMPACT_LABELS[impact] : '—'}
          tone={impact === 'high' ? 'warning' : 'default'}
        />
        <MetaItem
          icon="alert-outline" label="Rimando"
          value={risk ? RISK_LABELS[risk] : '—'}
          tone={risk === 'high' ? 'error' : risk === 'medium' ? 'warning' : 'default'}
        />
        {decision.deadline ? (
          <MetaItem icon="calendar-outline" label="Scadenza" value={formatDateTime(decision.deadline)} />
        ) : null}
        {conf ? <MetaItem icon="stats-chart-outline" label="Confidenza" value={CONFIDENCE_LABELS[conf]} /> : null}
      </View>

      {explainEnabled ? (
        <Pressable
          style={({ pressed }) => [styles.whyBtn, pressed && styles.pressed]}
          onPress={onWhy}
          accessibilityRole="button"
          accessibilityLabel="Mostra il ragionamento della priorità"
          testID="why-now-btn"
          hitSlop={8}
        >
          <Ionicons name="bulb-outline" size={16} color={tokens.color.onSurface} />
          <Text style={styles.whyBtnText}>Perché adesso?</Text>
          <Ionicons name="chevron-forward" size={14} color={tokens.color.onSurfaceMuted} />
        </Pressable>
      ) : null}

      {actionEnabled ? (
        <View style={styles.actions}>
          {!inProgress && !partial && (
            <ActionBtn
              primary label="Inizia" icon="play" onPress={onStart}
              loading={actionBusy?.startsWith('start:')} testID="btn-start"
            />
          )}
          <ActionBtn label="Risolvi" icon="checkmark" onPress={onComplete} loading={actionBusy?.startsWith('complete:')} testID="btn-complete" />
          <ActionBtn label="Parziale" icon="pie-chart-outline" onPress={onPartial} testID="btn-partial" />
          <ActionBtn label="Rimanda" icon="hourglass-outline" onPress={onPostpone} testID="btn-postpone" />
          <ActionBtn label="Altro" icon="ellipsis-horizontal" onPress={onMore} testID="btn-more" />
        </View>
      ) : null}
    </View>
  );
}

function MetaItem({ icon, label, value, tone }: {
  icon: any; label: string; value: string; tone?: 'error' | 'warning' | 'success' | 'default';
}) {
  const bg =
    tone === 'error' ? tokens.color.errorBg :
    tone === 'warning' ? tokens.color.warningBg :
    tone === 'success' ? tokens.color.successBg :
    tokens.color.surfaceTertiary;
  const color =
    tone === 'error' ? tokens.color.error :
    tone === 'warning' ? tokens.color.warning :
    tone === 'success' ? tokens.color.success :
    tokens.color.onSurface;
  return (
    <View style={[styles.meta, { backgroundColor: bg }]} accessible accessibilityLabel={`${label}: ${value}`}>
      <Ionicons name={icon} size={13} color={tokens.color.onSurfaceMuted} />
      <Text style={styles.metaLabel}>{label}</Text>
      <Text style={[styles.metaValue, { color }]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: tokens.radius.lg,
    padding: tokens.spacing.lg,
    gap: tokens.spacing.md,
    borderWidth: 1,
    borderColor: tokens.color.borderStrong,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.25,
    shadowRadius: 12,
    elevation: 4,
  },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  pill: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: 10, paddingVertical: 5,
    borderRadius: tokens.radius.pill, backgroundColor: tokens.color.brand,
  },
  pillDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: tokens.color.onBrand },
  pillText: { fontSize: 10, fontWeight: '700', color: tokens.color.onBrand, letterSpacing: 1 },
  statusPill: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: 10, paddingVertical: 4,
    borderRadius: tokens.radius.pill, borderWidth: 1,
  },
  dot: { width: 6, height: 6, borderRadius: 3 },
  statusText: { fontSize: 11, color: tokens.color.onSurface, fontWeight: '500' },
  title: { fontSize: 24, fontWeight: '700', color: tokens.color.onSurface, lineHeight: 30, letterSpacing: -0.3 },
  desc: { fontSize: 14, color: tokens.color.onSurfaceMuted, lineHeight: 20 },
  summaryBox: {
    flexDirection: 'row', gap: 8, alignItems: 'flex-start',
    backgroundColor: tokens.color.surfaceTertiary,
    padding: 10, borderRadius: tokens.radius.md,
    borderLeftWidth: 2, borderLeftColor: tokens.color.brand,
  },
  summary: { flex: 1, fontSize: 13, color: tokens.color.onSurface, lineHeight: 19 },
  progressWrap: { gap: 6 },
  progressTrack: { width: '100%', height: 6, borderRadius: 3, backgroundColor: tokens.color.surfaceTertiary, overflow: 'hidden' },
  progressBar: { height: 6, borderRadius: 3 },
  progressLabel: { fontSize: 11, color: tokens.color.onSurfaceMuted, fontWeight: '500' },
  metaGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: tokens.spacing.sm },
  meta: {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    paddingHorizontal: 10, paddingVertical: 7, borderRadius: tokens.radius.md,
  },
  metaLabel: { fontSize: 11, color: tokens.color.onSurfaceMuted },
  metaValue: { fontSize: 12, color: tokens.color.onSurface, fontWeight: '600' },
  whyBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start',
    paddingHorizontal: 14, paddingVertical: 10,
    borderRadius: tokens.radius.pill, borderWidth: 1, borderColor: tokens.color.borderStrong,
    minHeight: tokens.touch.min, backgroundColor: tokens.color.surfaceTertiary,
  },
  whyBtnText: { fontSize: 13, color: tokens.color.onSurface, fontWeight: '600' },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 4 },
  pressed: { opacity: 0.7, transform: [{ scale: 0.98 }] },
});
