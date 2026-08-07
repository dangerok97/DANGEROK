import { useState } from 'react';
import { View, Text, StyleSheet, Pressable, Platform } from 'react-native';
import { useRouter } from 'expo-router';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { HomeActionDef, HomeExplanation, HomeItem } from '@/src/api/client';
import { ActionEngine } from '@/src/action-engine';
import { formatWhen } from '@/src/components/home/v2/homeNav';
import { DynamicActions } from '@/src/components/home/v2/DynamicActions';
import { triggerHaptic } from '@/src/theme/haptics';

type Props = {
  item: HomeItem;
  explanation?: HomeExplanation | null;
  busy?: string | null;
  onAction: (action: HomeActionDef) => void | Promise<void>;
  onCorrect?: () => void;
  onIgnore?: () => void;
};

const TYPE_LABELS: Record<string, string> = {
  bill: 'Bolletta',
  payment: 'Pagamento',
  event: 'Evento',
  visit: 'Visita',
  study: 'Studio',
  travel: 'Viaggio',
  needs_review: 'Da verificare',
  verify: 'Verifica',
  reply: 'Risposta',
  activity: 'Attività',
  generic: 'Priorità',
  resume: 'In corso',
};

const INTENT_LABELS: Record<string, string> = {
  study: 'Studio',
  exam_preparation: 'Studio · esame',
  travel: 'Viaggio',
  vacation: 'Viaggio',
  event: 'Evento',
  payment: 'Pagamento',
  financial: 'Pagamento',
  medical: 'Visita',
};

function typeLabel(item: HomeItem): string {
  const intent = (item.meta as { intent?: string } | undefined)?.intent;
  const subtype = item.subtype || '';
  return (
    INTENT_LABELS[intent || ''] ||
    INTENT_LABELS[subtype] ||
    TYPE_LABELS[item.card_type || ''] ||
    TYPE_LABELS[item.type] ||
    item.type
  );
}

/** Pick ≤3 meta lines that explain why this matters now. */
function focusMeta(item: HomeItem): string[] {
  const lines: string[] = [];
  const when = formatWhen(item.start_at || item.due_at || item.goal_target_date);
  if (when) {
    lines.push(item.due_at && !item.start_at ? `Scade ${when}` : when);
  }
  if (item.amount) lines.push(item.amount);
  else if (item.location) lines.push(item.location);
  if (item.goal_blockers?.[0]) lines.push(item.goal_blockers[0]);
  else if (item.goal_next_action) lines.push(item.goal_next_action);
  else if (item.goal_progress_label) lines.push(item.goal_progress_label);
  else if (item.duration_minutes) lines.push(`${item.duration_minutes} min`);
  return lines.slice(0, 3);
}

/**
 * Daily Focus hero — singular Focus Glow, progressive disclosure.
 * Preserves adesso-card / perche-adesso / dynamic-actions testIDs.
 */
export function DailyFocus({
  item,
  explanation,
  busy,
  onAction,
  onCorrect,
  onIgnore,
}: Props) {
  const { colors, shadow } = useTheme();
  const router = useRouter();
  const [whyOpen, setWhyOpen] = useState(false);
  const meta = focusMeta(item);
  const context =
    item.subtitle && item.subtitle !== item.description
      ? item.subtitle
      : item.description
        ? item.description
        : null;
  const details =
    item.supporting_details ||
    ((item.meta as { supporting_details?: { label?: string }[] } | undefined)?.supporting_details);

  const primary = (item.actions || []).find((a) => a.primary) || (item.actions || [])[0];
  const secondary = (item.actions || []).filter((a) => a.id !== primary?.id);

  return (
    <View
      style={[
        styles.glowWrap,
        Platform.OS === 'web'
          ? ({ boxShadow: `0 0 36px ${colors.focusGlow}` } as object)
          : {
              shadowColor: colors.accent,
              shadowOpacity: 0.22,
              shadowRadius: 28,
              shadowOffset: { width: 0, height: 8 },
            },
      ]}
      testID="daily-focus"
    >
      <Pressable
        style={({ pressed }) => [
          styles.card,
          {
            backgroundColor: colors.surfaceElevated,
            borderColor: colors.border,
            opacity: pressed ? 0.96 : 1,
            transform: [{ scale: pressed ? 0.985 : 1 }],
          },
          shadow('soft'),
        ]}
        onPress={async () => {
          void triggerHaptic('impactLight');
          await ActionEngine.open(item, router);
        }}
        accessibilityRole="button"
        accessibilityLabel={`Apri guida per ${item.title}`}
        testID="adesso-card"
      >
        <View style={styles.eyebrowRow}>
          <Text style={[styles.eyebrow, { color: colors.accent }]}>Adesso</Text>
          <Text style={[styles.type, { color: colors.textTertiary }]}>{typeLabel(item)}</Text>
        </View>

        <Text
          style={[styles.title, { color: colors.textPrimary }]}
          accessibilityRole="header"
          numberOfLines={3}
        >
          {item.title}
        </Text>

        {context ? (
          <Text
            style={[styles.context, { color: colors.textSecondary }]}
            numberOfLines={3}
            testID={
              item.subtitle && item.subtitle !== item.description
                ? 'adesso-subtitle'
                : undefined
            }
          >
            {context}
          </Text>
        ) : null}

        {item.goal_title && !(item.description || '').includes('Obiettivo:') ? (
          <Text style={[styles.goal, { color: colors.textTertiary }]} testID="adesso-goal-context">
            {item.goal_title}
          </Text>
        ) : null}

        {meta.length ? (
          <View style={styles.metaRow}>
            {meta.map((m) => (
              <Text key={m} style={[styles.meta, { color: colors.textSecondary }]} numberOfLines={1}>
                {m}
              </Text>
            ))}
          </View>
        ) : null}

        {Array.isArray(details) && details.length > 0 ? (
          <View style={styles.detailsHidden} testID="adesso-supporting-details">
            {details.slice(0, 4).map((d, idx) => (
              <Text key={`${d.label || 'd'}-${idx}`} style={{ height: 0, opacity: 0 }}>
                {d.label}
              </Text>
            ))}
          </View>
        ) : null}
      </Pressable>

      {/* Primary action row — DynamicActions keeps all kinds + testIDs */}
      <View style={styles.actionsBlock}>
        <DynamicActions
          item={{
            ...item,
            actions: primary
              ? [primary, ...secondary]
              : item.actions,
          }}
          busy={busy}
          onAction={onAction}
        />
      </View>

      {explanation?.summary || explanation?.factors?.length ? (
        <View
          style={[styles.why, { borderTopColor: colors.divider }]}
          testID="perche-adesso"
        >
          <Pressable
            onPress={() => setWhyOpen((v) => !v)}
            accessibilityRole="button"
            accessibilityState={{ expanded: whyOpen }}
            accessibilityLabel="Perché ora"
            style={styles.whyHead}
          >
            <Text style={[styles.whyLabel, { color: colors.textTertiary }]}>Perché ora</Text>
            <Text style={[styles.whySummary, { color: colors.textSecondary }]} numberOfLines={whyOpen ? 8 : 2}>
              {explanation.summary || explanation.factors?.[0]?.label}
            </Text>
            <Text style={[styles.whyToggle, { color: colors.accent }]}>
              {whyOpen ? 'Meno' : 'Perché adesso?'}
            </Text>
          </Pressable>

          {whyOpen && explanation.factors?.length ? (
            <View style={styles.whyBody}>
              {explanation.factors.slice(0, 4).map((f) => (
                <Text key={`${f.code}-${f.label}`} style={[styles.factor, { color: colors.textSecondary }]}>
                  · {f.label}{f.detail ? ` — ${f.detail}` : ''}
                </Text>
              ))}
            </View>
          ) : null}

          <View style={styles.whyActionsCompact}>
            {onCorrect ? (
              <Pressable
                onPress={onCorrect}
                testID="btn-correct-priority"
                accessibilityRole="button"
                style={styles.linkHit}
              >
                <Text style={[styles.link, { color: colors.textTertiary }]}>Correggi priorità</Text>
              </Pressable>
            ) : null}
            {onIgnore ? (
              <Pressable
                onPress={onIgnore}
                testID="btn-ignore-focus"
                accessibilityRole="button"
                style={styles.linkHit}
              >
                <Text style={[styles.link, { color: colors.textTertiary }]}>Ignora</Text>
              </Pressable>
            ) : null}
          </View>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  glowWrap: {
    borderRadius: tokens.radius.xl,
    gap: tokens.spacing.md,
  },
  card: {
    borderRadius: tokens.radius.xl,
    borderWidth: StyleSheet.hairlineWidth,
    padding: tokens.spacing.xl,
    gap: tokens.spacing.sm,
  },
  eyebrowRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 4,
  },
  eyebrow: {
    fontSize: tokens.typography.label.fontSize,
    fontWeight: '600',
    letterSpacing: 0.4,
  },
  type: {
    fontSize: tokens.typography.footnote.fontSize,
    fontWeight: '500',
  },
  title: {
    fontSize: tokens.typography.hero.fontSize,
    fontWeight: tokens.typography.hero.fontWeight,
    letterSpacing: tokens.typography.hero.letterSpacing,
    lineHeight: tokens.typography.hero.lineHeight,
  },
  context: {
    fontSize: tokens.typography.bodySmall.fontSize,
    lineHeight: tokens.typography.bodySmall.lineHeight,
  },
  goal: {
    fontSize: tokens.typography.caption.fontSize,
  },
  metaRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: tokens.spacing.md,
    marginTop: tokens.spacing.xs,
  },
  meta: {
    fontSize: tokens.typography.caption.fontSize,
  },
  detailsHidden: { height: 0, overflow: 'hidden' },
  actionsBlock: { paddingHorizontal: 2 },
  why: {
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingTop: tokens.spacing.md,
    gap: tokens.spacing.sm,
  },
  whyHead: { gap: 4 },
  whyLabel: {
    fontSize: tokens.typography.footnote.fontSize,
    fontWeight: '600',
    letterSpacing: 0.3,
  },
  whySummary: {
    fontSize: tokens.typography.bodySmall.fontSize,
    lineHeight: tokens.typography.bodySmall.lineHeight,
  },
  whyToggle: {
    fontSize: tokens.typography.caption.fontSize,
    fontWeight: '600',
    marginTop: 2,
  },
  whyBody: { gap: 6 },
  factor: {
    fontSize: tokens.typography.caption.fontSize,
    lineHeight: 18,
  },
  whyActionsCompact: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: tokens.spacing.lg,
    marginTop: 2,
  },
  linkHit: { minHeight: tokens.touch.min, justifyContent: 'center' },
  link: {
    fontSize: tokens.typography.caption.fontSize,
    fontWeight: '500',
  },
});
