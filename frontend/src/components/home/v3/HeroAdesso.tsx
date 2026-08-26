import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import type { HomeActionDef, HomeExplanation, HomeItem } from '@/src/api/client';
import { ContextualCardVisual } from './ContextualCardVisual';
import { primaryActionOf, overflowActionsOf, whenLabel } from './homeItemView';

type Props = {
  item: HomeItem;
  explanation?: HomeExplanation | null;
  busy?: string | null;
  wide: boolean;
  onAction: (action: HomeActionDef) => void;
  onSnooze: () => void;
  onCorrect: () => void;
  onIgnore: () => void;
};

/**
 * ADESSO — the one thing that matters now.
 *
 * The whole Home is arranged so this card can be understood without scrolling
 * and acted on without deciding. That is why it carries exactly one primary
 * action: the previous Home offered Continua / Apri / Rimanda / Ignora as four
 * equal buttons, which turns "what should I do" into a menu, at the precise
 * moment the product is supposed to have already answered it.
 *
 * Everything else is still reachable — secondary inline, the rest behind the
 * overflow — but nothing else competes.
 */
export function HeroAdesso({
  item,
  explanation,
  busy,
  wide,
  onAction,
  onSnooze,
  onCorrect,
  onIgnore,
}: Props) {
  const { colors } = useTheme();
  const [whyOpen, setWhyOpen] = useState(false);
  const [overflowOpen, setOverflowOpen] = useState(false);

  const primary = primaryActionOf(item);
  const overflow = overflowActionsOf(item);
  const when = whenLabel(item);
  const why = explanation?.summary || item.reason_summary || null;
  const supporting = (item.supporting_details || []).slice(0, 2);

  return (
    <View
      style={[styles.card, { backgroundColor: colors.surfaceWarm, borderColor: colors.divider }]}
      testID="home-hero"
    >
      <View style={[styles.body, wide && styles.bodyWide]}>
        <View style={styles.text}>
          <Text style={[styles.eyebrow, { color: colors.warning }]}>ADESSO</Text>

          <Text
            style={[styles.title, { color: colors.textPrimary }]}
            accessibilityRole="header"
            aria-level={2}
          >
            {item.title}
          </Text>

          {item.subtitle || item.description ? (
            <Text style={[styles.desc, { color: colors.textSecondary }]} numberOfLines={2}>
              {item.subtitle || item.description}
            </Text>
          ) : null}

          {when ? (
            <Text style={[styles.when, { color: colors.textTertiary }]}>{when}</Text>
          ) : null}

          {/*
            Whatever the payload already knows is still open, shown as things
            still to settle rather than as metadata. Nothing is invented: if
            the item carries no supporting details, this simply does not
            render and the card keeps its composition.
          */}
          {supporting.length ? (
            <View style={styles.supporting}>
              {supporting.map((d, i) => (
                <View
                  key={`${d.kind}-${i}`}
                  style={[styles.supportRow, { backgroundColor: colors.surface, borderColor: colors.divider }]}
                >
                  <View style={[styles.supportDot, { borderColor: colors.borderStrong }]} />
                  <Text style={[styles.supportLabel, { color: colors.textPrimary }]} numberOfLines={1}>
                    {d.label}
                  </Text>
                </View>
              ))}
            </View>
          ) : null}

          <View style={styles.actions}>
            {primary ? (
              <Pressable
                onPress={() => onAction(primary)}
                disabled={!!busy}
                style={({ pressed }) => [
                  styles.cta,
                  { backgroundColor: colors.accent },
                  pressed && styles.pressed,
                  !!busy && styles.disabled,
                ]}
                accessibilityRole="button"
                accessibilityLabel={primary.label}
                testID="home-hero-primary"
              >
                <Text style={[styles.ctaLabel, { color: colors.onAccent }]}>{primary.label}</Text>
                <Ionicons name="arrow-forward" size={16} color={colors.onAccent} />
              </Pressable>
            ) : null}

            {why ? (
              <Pressable
                onPress={() => setWhyOpen((v) => !v)}
                style={({ pressed }) => [styles.ghost, pressed && styles.pressed]}
                accessibilityRole="button"
                accessibilityState={{ expanded: whyOpen }}
                testID="home-hero-why"
              >
                <Text style={[styles.ghostLabel, { color: colors.textSecondary }]}>Perché ora?</Text>
              </Pressable>
            ) : null}

            {overflow.length || true ? (
              <Pressable
                onPress={() => setOverflowOpen((v) => !v)}
                style={({ pressed }) => [styles.overflowBtn, pressed && styles.pressed]}
                accessibilityRole="button"
                accessibilityLabel="Altre azioni"
                accessibilityState={{ expanded: overflowOpen }}
                testID="home-hero-overflow"
              >
                <Ionicons name="ellipsis-horizontal" size={18} color={colors.textTertiary} />
              </Pressable>
            ) : null}
          </View>

          {whyOpen && why ? (
            <Text
              style={[styles.why, { color: colors.textSecondary, borderLeftColor: colors.accentMuted }]}
              testID="home-hero-why-text"
            >
              {why}
            </Text>
          ) : null}

          {overflowOpen ? (
            <View style={[styles.overflowMenu, { borderColor: colors.divider }]} testID="home-hero-overflow-menu">
              {overflow.map((a) => (
                <Pressable
                  key={a.kind}
                  onPress={() => { setOverflowOpen(false); onAction(a); }}
                  style={({ pressed }) => [styles.overflowItem, pressed && styles.pressed]}
                  accessibilityRole="button"
                >
                  <Text style={[styles.overflowLabel, { color: colors.textSecondary }]}>{a.label}</Text>
                </Pressable>
              ))}
              <Pressable
                onPress={() => { setOverflowOpen(false); onSnooze(); }}
                style={({ pressed }) => [styles.overflowItem, pressed && styles.pressed]}
                accessibilityRole="button"
                testID="home-hero-snooze"
              >
                <Text style={[styles.overflowLabel, { color: colors.textSecondary }]}>Rimanda</Text>
              </Pressable>
              <Pressable
                onPress={() => { setOverflowOpen(false); onCorrect(); }}
                style={({ pressed }) => [styles.overflowItem, pressed && styles.pressed]}
                accessibilityRole="button"
              >
                <Text style={[styles.overflowLabel, { color: colors.textSecondary }]}>Cambia priorità</Text>
              </Pressable>
              <Pressable
                onPress={() => { setOverflowOpen(false); onIgnore(); }}
                style={({ pressed }) => [styles.overflowItem, pressed && styles.pressed]}
                accessibilityRole="button"
              >
                <Text style={[styles.overflowLabel, { color: colors.textSecondary }]}>Ignora</Text>
              </Pressable>
            </View>
          ) : null}
        </View>

        {/*
          The real generated image the moment it exists. The abstract
          composition is the state before it — missing, queued, generating,
          failed — never the intended final result.
        */}
        <ContextualCardVisual
          item={item}
          imageSource={item.visual?.status === 'ready' ? item.visual.url : null}
          generating={item.visual?.status === 'queued' || item.visual?.status === 'generating'}
          size="hero"
          style={wide ? styles.visualWide : styles.visualStacked}
          testID="home-hero-visual"
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: tokens.radius.xl,
    borderWidth: StyleSheet.hairlineWidth,
    overflow: 'hidden',
  },
  body: { flexDirection: 'column-reverse' },
  /** Desktop: text leads, picture anchors the right — as in the reference. */
  bodyWide: { flexDirection: 'row', alignItems: 'stretch' },
  text: {
    flex: 1,
    padding: tokens.spacing.xl,
    gap: tokens.spacing.sm,
  },
  /** Phone: full-bleed media on top of the card. */
  visualStacked: { width: '100%', height: 168, borderRadius: 0 },
  visualWide: { width: 300, alignSelf: 'stretch', borderRadius: 0 },
  eyebrow: {
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 1.4,
  },
  title: {
    fontSize: 29,
    fontWeight: '700',
    lineHeight: 36,
    letterSpacing: -0.7,
    maxWidth: 520,
  },
  desc: {
    fontSize: 15,
    lineHeight: 22,
  },
  when: { fontSize: 13, marginTop: 2 },
  supporting: { gap: 8, marginTop: tokens.spacing.md, maxWidth: 460 },
  supportRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: tokens.spacing.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.md,
    paddingHorizontal: tokens.spacing.lg,
    minHeight: 46,
  },
  supportDot: {
    width: 16,
    height: 16,
    borderRadius: 8,
    borderWidth: 1.5,
  },
  supportLabel: { fontSize: 14, flex: 1 },
  actions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: tokens.spacing.sm,
    marginTop: tokens.spacing.md,
    flexWrap: 'wrap',
  },
  cta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    minHeight: tokens.touch.min,
    paddingHorizontal: tokens.spacing.xl,
    borderRadius: tokens.radius.md,
  },
  ctaLabel: { fontSize: 15, fontWeight: '600' },
  ghost: {
    minHeight: tokens.touch.min,
    justifyContent: 'center',
    paddingHorizontal: tokens.spacing.md,
  },
  ghostLabel: { fontSize: 14, fontWeight: '500' },
  overflowBtn: {
    minHeight: tokens.touch.min,
    minWidth: tokens.touch.min,
    alignItems: 'center',
    justifyContent: 'center',
  },
  why: {
    fontSize: 14,
    lineHeight: 21,
    borderLeftWidth: 2,
    paddingLeft: tokens.spacing.md,
    marginTop: tokens.spacing.sm,
  },
  overflowMenu: {
    marginTop: tokens.spacing.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.md,
    overflow: 'hidden',
  },
  overflowItem: {
    minHeight: tokens.touch.min,
    justifyContent: 'center',
    paddingHorizontal: tokens.spacing.lg,
  },
  overflowLabel: { fontSize: 14 },
  pressed: { opacity: 0.7 },
  disabled: { opacity: 0.5 },
});
