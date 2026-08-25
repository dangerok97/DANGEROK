import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import type { MaterialView, PlanItemView } from './planView';

/* -------------------------------------------------------------------------- */
/* Header — compact. This is a work surface, not a landing page.               */
/* -------------------------------------------------------------------------- */

export function WorkspaceHeader({
  title,
  outcome,
  horizon,
  onBack,
}: {
  /** Absent while we do not yet know which goal this is. */
  title?: string | null;
  outcome?: string | null;
  horizon?: string | null;
  onBack: () => void;
}) {
  const { colors } = useTheme();
  return (
    <View style={styles.header} testID="workspace-header">
      <Pressable
        onPress={onBack}
        hitSlop={12}
        style={({ pressed }) => [styles.back, pressed && styles.pressed]}
        accessibilityRole="button"
        accessibilityLabel="Torna indietro"
      >
        <Ionicons name="chevron-back" size={20} color={colors.textSecondary} />
      </Pressable>
      <View style={styles.headerText}>
        <Text style={[styles.eyebrow, { color: colors.textTertiary }]}>WORKSPACE</Text>
        {title ? (
          <Text
            style={[styles.title, { color: colors.textPrimary }]}
            accessibilityRole="header"
            aria-level={1}
          >
            {title}
          </Text>
        ) : null}
        {outcome ? (
          <Text style={[styles.outcome, { color: colors.textSecondary }]} numberOfLines={2}>
            {outcome}
          </Text>
        ) : null}
        {horizon ? (
          <Text style={[styles.horizon, { color: colors.textTertiary }]}>Entro il {horizon}</Text>
        ) : null}
      </View>
    </View>
  );
}

/* -------------------------------------------------------------------------- */
/* ADESSO — the one concrete next step                                        */
/* -------------------------------------------------------------------------- */

export function CurrentStep({
  title,
  detail,
  ctaLabel,
  onPress,
}: {
  title: string;
  detail?: string | null;
  ctaLabel: string;
  onPress: () => void;
}) {
  const { colors } = useTheme();
  return (
    <View
      style={[styles.now, { backgroundColor: colors.surfaceWarm, borderColor: colors.divider }]}
      testID="workspace-current-step"
    >
      <Text style={[styles.nowEyebrow, { color: colors.warning }]}>ADESSO</Text>
      <Text style={[styles.nowTitle, { color: colors.textPrimary }]}>{title}</Text>
      {detail ? (
        <Text style={[styles.nowDetail, { color: colors.textSecondary }]} numberOfLines={3}>
          {detail}
        </Text>
      ) : null}
      <Pressable
        onPress={onPress}
        style={({ pressed }) => [styles.cta, { backgroundColor: colors.accent }, pressed && styles.pressed]}
        accessibilityRole="button"
        testID="workspace-current-cta"
      >
        <Text style={[styles.ctaLabel, { color: colors.onAccent }]}>{ctaLabel}</Text>
        <Ionicons name="arrow-forward" size={16} color={colors.onAccent} />
      </Pressable>
    </View>
  );
}

/** Nothing left to do — said once, plainly, instead of a phantom "next step". */
export function PlanComplete({ onBack }: { onBack: () => void }) {
  const { colors } = useTheme();
  return (
    <View
      style={[styles.now, { backgroundColor: colors.successBg, borderColor: colors.divider }]}
      testID="workspace-complete"
    >
      <Text style={[styles.nowEyebrow, { color: colors.success }]}>COMPLETATO</Text>
      <Text style={[styles.nowTitle, { color: colors.textPrimary }]}>
        Hai portato a termine tutto.
      </Text>
      <Text style={[styles.nowDetail, { color: colors.textSecondary }]}>
        Il lavoro resta qui, se ti serve riprenderlo.
      </Text>
      <Pressable
        onPress={onBack}
        style={({ pressed }) => [styles.ghostCta, { borderColor: colors.border }, pressed && styles.pressed]}
        accessibilityRole="button"
      >
        <Text style={[styles.ghostLabel, { color: colors.textPrimary }]}>Torna alla Home</Text>
      </Pressable>
    </View>
  );
}

/* -------------------------------------------------------------------------- */
/* Materials — how you move between what ORA has made                          */
/* -------------------------------------------------------------------------- */

export function MaterialSelector({
  materials,
  activeId,
  onSelect,
}: {
  materials: MaterialView[];
  activeId?: string | null;
  onSelect: (id: string) => void;
}) {
  const { colors } = useTheme();
  // One material needs no chooser — the chooser would be the only thing to
  // choose from, which is furniture, not navigation.
  if (materials.length < 2) return null;

  return (
    <View style={styles.materials} testID="workspace-materials">
      <Text style={[styles.sectionLabel, { color: colors.textTertiary }]}>MATERIALI</Text>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.chipScroll}
        contentContainerStyle={styles.chipRow}
        accessibilityRole="tablist"
      >
        {materials.map((m) => {
          const active = m.id === activeId;
          return (
            <Pressable
              key={m.id}
              onPress={() => onSelect(m.id)}
              style={({ pressed }) => [
                styles.chip,
                {
                  backgroundColor: active ? colors.accentMuted : colors.surface,
                  borderColor: active ? colors.accent : colors.border,
                },
                pressed && styles.pressed,
              ]}
              accessibilityRole="tab"
              accessibilityState={{ selected: active }}
              aria-selected={active}
              testID={`workspace-material-${m.id}`}
            >
              <Text
                style={[
                  styles.chipLabel,
                  { color: active ? colors.accent : colors.textSecondary },
                  active && { fontWeight: '600' },
                ]}
                numberOfLines={1}
              >
                {m.title}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>
    </View>
  );
}

/* -------------------------------------------------------------------------- */
/* Plan progression — secondary to the work itself                             */
/* -------------------------------------------------------------------------- */

export function PlanProgress({ steps }: { steps: PlanItemView[] }) {
  const { colors } = useTheme();
  if (!steps.length) return null;

  const done = steps.filter((s) => s.state === 'done').length;

  return (
    <View
      style={[styles.panel, { backgroundColor: colors.surface, borderColor: colors.border }]}
      testID="workspace-progress"
    >
      <View style={styles.panelHead}>
        <Text style={[styles.sectionLabel, { color: colors.textSecondary }]}>DOVE SIAMO</Text>
        {/*
          A count of steps, not a percentage. "3 di 7" is something a person can
          picture; "43%" is a number about the plan rather than about them.
        */}
        <Text style={[styles.countLabel, { color: colors.textTertiary }]}>
          {done} di {steps.length}
        </Text>
      </View>

      {steps.map((s) => {
        const isNow = s.state === 'now';
        const isDone = s.state === 'done';
        return (
          <View key={s.id} style={styles.stepRow}>
            {/* Shape as well as colour: done is filled, now is ringed, next is hollow. */}
            <View
              style={[
                styles.marker,
                isDone && { backgroundColor: colors.success, borderColor: colors.success },
                isNow && { borderColor: colors.accent, borderWidth: 2.5 },
                !isDone && !isNow && { borderColor: colors.borderStrong },
              ]}
            >
              {isDone ? <Ionicons name="checkmark" size={10} color={colors.onAccent} /> : null}
            </View>
            <View style={styles.stepText}>
              <Text
                style={[
                  styles.stepTitle,
                  { color: isDone ? colors.textTertiary : colors.textPrimary },
                  isNow && { fontWeight: '600' },
                  isDone && { textDecorationLine: 'line-through' },
                ]}
                numberOfLines={2}
              >
                {s.title}
              </Text>
              {s.when ? (
                <Text style={[styles.stepWhen, { color: colors.textTertiary }]}>{s.when}</Text>
              ) : null}
            </View>
          </View>
        );
      })}
    </View>
  );
}

/* -------------------------------------------------------------------------- */
/* Sources — useful, never in the way                                          */
/* -------------------------------------------------------------------------- */

export function WorkspaceSources({
  sources,
}: {
  sources: Array<{ name: string; authority: string }>;
}) {
  const { colors } = useTheme();
  if (!sources.length) return null;

  return (
    <View
      style={[styles.panel, { backgroundColor: colors.surface, borderColor: colors.border }]}
      testID="workspace-sources"
    >
      <Text style={[styles.sectionLabel, { color: colors.textSecondary }]}>FONTI USATE</Text>
      {sources.slice(0, 8).map((s) => (
        <View key={s.name} style={styles.sourceRow}>
          <Ionicons name="document-text-outline" size={15} color={colors.textTertiary} />
          <View style={styles.stepText}>
            <Text style={[styles.sourceName, { color: colors.textPrimary }]} numberOfLines={1}>
              {s.name}
            </Text>
            {s.authority ? (
              <Text style={[styles.stepWhen, { color: colors.textTertiary }]} numberOfLines={1}>
                {s.authority}
              </Text>
            ) : null}
          </View>
        </View>
      ))}
    </View>
  );
}

/* -------------------------------------------------------------------------- */

const styles = StyleSheet.create({
  header: { flexDirection: 'row', gap: tokens.spacing.sm, alignItems: 'flex-start' },
  back: {
    // Full touch target, pulled back into the margin so the title still starts
    // on the page's left edge rather than indented by the button.
    width: tokens.touch.min, height: tokens.touch.min,
    alignItems: 'center', justifyContent: 'center',
    marginLeft: -12, marginTop: -4,
  },
  headerText: { flex: 1, gap: 3 },
  eyebrow: { fontSize: 11, fontWeight: '700', letterSpacing: 1.3 },
  title: { fontSize: 24, fontWeight: '700', lineHeight: 30, letterSpacing: -0.5 },
  outcome: { fontSize: 15, lineHeight: 21 },
  horizon: { fontSize: 13, marginTop: 2 },

  now: {
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    padding: tokens.spacing.xl,
    gap: tokens.spacing.sm,
  },
  nowEyebrow: { fontSize: 11, fontWeight: '700', letterSpacing: 1.4 },
  nowTitle: { fontSize: 19, fontWeight: '600', lineHeight: 26 },
  nowDetail: { fontSize: 14, lineHeight: 21 },
  cta: {
    flexDirection: 'row', alignItems: 'center', gap: 8, alignSelf: 'flex-start',
    minHeight: tokens.touch.min, paddingHorizontal: tokens.spacing.xl,
    borderRadius: tokens.radius.md, marginTop: tokens.spacing.sm,
  },
  ctaLabel: { fontSize: 15, fontWeight: '600' },
  ghostCta: {
    alignSelf: 'flex-start', minHeight: tokens.touch.min, justifyContent: 'center',
    paddingHorizontal: tokens.spacing.xl, borderRadius: tokens.radius.md,
    borderWidth: StyleSheet.hairlineWidth, marginTop: tokens.spacing.sm,
  },
  ghostLabel: { fontSize: 14, fontWeight: '600' },

  materials: { gap: tokens.spacing.sm },
  /** A horizontal scroller must never be vertically compressible (PX1.1). */
  chipScroll: { flexGrow: 0, flexShrink: 0 },
  chipRow: { gap: tokens.spacing.sm, paddingRight: tokens.spacing.lg },
  chip: {
    borderWidth: StyleSheet.hairlineWidth, borderRadius: tokens.radius.pill,
    paddingHorizontal: tokens.spacing.lg, minHeight: tokens.touch.min,
    justifyContent: 'center', maxWidth: 220,
  },
  chipLabel: { fontSize: 13 },

  panel: {
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    padding: tokens.spacing.lg,
    gap: tokens.spacing.sm,
  },
  panelHead: { flexDirection: 'row', alignItems: 'center' },
  sectionLabel: { fontSize: 11, fontWeight: '700', letterSpacing: 1.2, flex: 1 },
  countLabel: { fontSize: 12, fontWeight: '600' },
  stepRow: { flexDirection: 'row', gap: tokens.spacing.md, alignItems: 'flex-start', minHeight: 34 },
  marker: {
    width: 16, height: 16, borderRadius: 8, borderWidth: 1.5,
    alignItems: 'center', justifyContent: 'center', marginTop: 2,
  },
  stepText: { flex: 1, gap: 1 },
  stepTitle: { fontSize: 14, lineHeight: 20 },
  stepWhen: { fontSize: 12 },
  sourceRow: { flexDirection: 'row', gap: tokens.spacing.md, alignItems: 'center', minHeight: 36 },
  sourceName: { fontSize: 14 },
  pressed: { opacity: 0.75 },
});
