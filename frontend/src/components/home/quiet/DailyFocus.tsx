import { useState } from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { useRouter } from 'expo-router';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { getFocusGlow } from '@/src/theme/focusGlow';
import { HomeActionDef, HomeExplanation, HomeItem } from '@/src/api/client';
import { ActionEngine } from '@/src/action-engine';
import { FocusActions } from './FocusActions';
import { focusMeta, typeLabel } from './focusPresentation';
import { triggerHaptic } from '@/src/theme/haptics';

type Props = {
  item: HomeItem;
  explanation?: HomeExplanation | null;
  busy?: string | null;
  onAction: (action: HomeActionDef) => void | Promise<void>;
  onCorrect?: () => void;
  onIgnore?: () => void;
};

/**
 * Daily Focus — page surface, not a windowed card.
 * Singular Focus Glow; editorial “Perché adesso”; CTA hierarchy via FocusActions.
 */
export function DailyFocus({
  item,
  explanation,
  busy,
  onAction,
  onCorrect,
  onIgnore,
}: Props) {
  const { colors, scheme } = useTheme();
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
  const softBorder = scheme === 'dark' ? 'rgba(255,255,255,0.04)' : 'rgba(28,28,30,0.04)';

  // Backend Presentation Semantics: explanation.summary is human Italian.
  const whySummary = explanation?.summary || null;
  const showWhy = Boolean(whySummary || explanation?.factors?.length);

  return (
    <View style={[styles.glowWrap, getFocusGlow(scheme) as object]} testID="daily-focus">
      <Pressable
        style={({ pressed }) => [
          styles.surface,
          {
            backgroundColor: colors.surface,
            borderColor: softBorder,
            opacity: pressed ? 0.97 : 1,
          },
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
          <Text style={[styles.eyebrow, { color: colors.textTertiary }]}>Adesso</Text>
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
            numberOfLines={2}
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
              <Text key={m} style={[styles.meta, { color: colors.textTertiary }]} numberOfLines={1}>
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

      <View style={styles.actionsBlock}>
        <FocusActions
          item={{
            ...item,
            actions: primary ? [primary, ...secondary] : item.actions,
          }}
          busy={busy}
          onAction={onAction}
        />
      </View>

      {showWhy ? (
        <View style={styles.why} testID="perche-adesso">
          <Pressable
            onPress={() => setWhyOpen((v) => !v)}
            accessibilityRole="button"
            accessibilityState={{ expanded: whyOpen }}
            accessibilityLabel="Perché adesso"
            style={styles.whyHead}
          >
            <Text style={[styles.whyLabel, { color: colors.textTertiary }]}>Perché adesso</Text>
            {whySummary ? (
              <Text
                style={[styles.whySummary, { color: colors.textSecondary }]}
                numberOfLines={whyOpen ? 8 : 2}
              >
                {whySummary}
              </Text>
            ) : null}
          </Pressable>

          {whyOpen && explanation?.factors?.length ? (
            <View style={styles.whyBody}>
              {explanation.factors.slice(0, 3).map((f) => (
                <Text
                  key={`${f.code}-${f.label}`}
                  style={[styles.factor, { color: colors.textTertiary }]}
                >
                  {f.label}
                  {f.detail ? ` — ${f.detail}` : ''}
                </Text>
              ))}
            </View>
          ) : null}

          <View style={styles.whyActions}>
            {onCorrect ? (
              <Pressable
                onPress={onCorrect}
                testID="btn-correct-priority"
                accessibilityRole="button"
                style={styles.linkHit}
              >
                <Text style={[styles.link, { color: colors.textTertiary }]}>Correggi</Text>
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
            <Text style={styles.srOnly}>Perché adesso?</Text>
          </View>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  glowWrap: {
    borderRadius: tokens.radius.lg,
    gap: tokens.spacing.lg,
    paddingVertical: tokens.spacing.sm,
  },
  surface: {
    borderRadius: tokens.radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    paddingVertical: tokens.spacing.lg,
    paddingHorizontal: 2,
    gap: tokens.spacing.sm,
  },
  eyebrowRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  eyebrow: {
    fontSize: tokens.typography.footnote.fontSize,
    fontWeight: '500',
    letterSpacing: 0.2,
  },
  type: {
    fontSize: tokens.typography.footnote.fontSize,
    fontWeight: '400',
  },
  title: {
    fontSize: tokens.typography.hero.fontSize,
    fontWeight: '700',
    letterSpacing: tokens.typography.hero.letterSpacing,
    lineHeight: tokens.typography.hero.lineHeight,
    marginTop: 2,
  },
  context: {
    fontSize: tokens.typography.bodySmall.fontSize,
    lineHeight: tokens.typography.bodySmall.lineHeight,
    marginTop: 2,
  },
  goal: {
    fontSize: tokens.typography.footnote.fontSize,
  },
  metaRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: tokens.spacing.md,
    marginTop: tokens.spacing.xs,
  },
  meta: {
    fontSize: tokens.typography.footnote.fontSize,
    fontWeight: '400',
  },
  detailsHidden: { height: 0, overflow: 'hidden' },
  actionsBlock: { paddingTop: 2 },
  why: {
    gap: tokens.spacing.sm,
    paddingTop: 2,
  },
  whyHead: { gap: 6 },
  whyLabel: {
    fontSize: 11,
    fontWeight: '500',
    letterSpacing: 0.15,
  },
  whySummary: {
    fontSize: tokens.typography.bodySmall.fontSize,
    lineHeight: 22,
    fontWeight: '400',
  },
  whyBody: { gap: 4 },
  factor: {
    fontSize: tokens.typography.footnote.fontSize,
    lineHeight: 17,
  },
  whyActions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: tokens.spacing.xl,
    marginTop: 2,
  },
  linkHit: { minHeight: tokens.touch.min, justifyContent: 'center' },
  link: {
    fontSize: tokens.typography.caption.fontSize,
    fontWeight: '400',
  },
  srOnly: {
    position: 'absolute',
    width: 1,
    height: 1,
    opacity: 0,
  },
});
