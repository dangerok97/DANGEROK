import * as React from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { AccountEntry } from '@/src/shell';

/* -------------------------------------------------------------------------- */
/* Header                                                                     */
/* -------------------------------------------------------------------------- */

export function VitaHeader({ onWhy }: { onWhy: () => void }) {
  const { colors } = useTheme();
  return (
    <View style={styles.header} testID="vita-header">
      <View style={styles.headerText}>
        <Text
          style={[styles.title, { color: colors.textPrimary }]}
          accessibilityRole="header"
          aria-level={1}
        >
          Vita
        </Text>
        <Text style={[styles.sub, { color: colors.textSecondary }]}>
          Quello che ORA sa della tua vita, cosa è attuale e cosa tenere a mente.
        </Text>
      </View>
      <Pressable
        onPress={onWhy}
        style={({ pressed }) => [
          styles.whyBtn,
          { backgroundColor: colors.surface, borderColor: colors.border },
          pressed && styles.pressed,
        ]}
        accessibilityRole="button"
        testID="vita-why"
      >
        <Ionicons name="sparkles-outline" size={14} color={colors.accent} />
        <Text style={[styles.whyLabel, { color: colors.textSecondary }]}>Perché conta?</Text>
      </Pressable>
      {/*
        Account, where a phone can reach it. Renders nothing on desktop, where
        the rail already answers this at its foot.
      */}
      <AccountEntry testID="vita-account" />
    </View>
  );
}

/**
 * Why ORA keeps any of this.
 *
 * Four sentences about what the user gets and what they control. No mention of
 * how it is stored, because the honest answer to "why does it matter" is about
 * the person's day, not about the architecture behind it.
 */
export function WhyItMattersDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { colors } = useTheme();
  const lines = [
    'ORA usa quello che sa per capire cosa conta adesso e cosa può aspettare.',
    'Collega fra loro impegni, documenti e obiettivi, così le cose non restano scollegate.',
    'Evita di richiederti informazioni che le hai già dato.',
    'Se qualcosa non è giusto, puoi correggerlo: decidi tu cosa ORA tiene a mente.',
  ];
  return (
    <Modal visible={open} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable
        style={[styles.scrim, { backgroundColor: colors.scrim }]}
        onPress={onClose}
        accessibilityLabel="Chiudi"
      >
        <View
          style={[
            styles.dialog,
            { backgroundColor: colors.surfaceElevated, borderColor: colors.border },
          ]}
          onStartShouldSetResponder={() => true}
          accessibilityViewIsModal
          testID="vita-why-dialog"
        >
          <View style={styles.dialogHead}>
            <Text
              style={[styles.dialogTitle, { color: colors.textPrimary }]}
              accessibilityRole="header"
              aria-level={2}
            >
              Perché conta
            </Text>
            <Pressable
              onPress={onClose}
              hitSlop={8}
              style={({ pressed }) => [styles.close, pressed && styles.pressed]}
              accessibilityRole="button"
              accessibilityLabel="Chiudi"
              testID="vita-why-close"
            >
              <Ionicons name="close" size={20} color={colors.textTertiary} />
            </Pressable>
          </View>
          {lines.map((l) => (
            <Text key={l} style={[styles.dialogLine, { color: colors.textSecondary }]}>
              {l}
            </Text>
          ))}
        </View>
      </Pressable>
    </Modal>
  );
}

/* -------------------------------------------------------------------------- */
/* Update strip                                                               */
/* -------------------------------------------------------------------------- */

/**
 * The invitation to keep ORA current.
 *
 * The action opens a conversation, not a form. A form would need categories,
 * and categories would need a taxonomy — the exact thing this page refuses to
 * impose. "Ho cambiato lavoro" is something a person can say; it is not
 * something they should have to find a field for.
 */
export function GrowStrip({ onUpdate }: { onUpdate: () => void }) {
  const { colors } = useTheme();
  return (
    <View
      style={[styles.strip, { backgroundColor: colors.surface, borderColor: colors.border }]}
      testID="vita-grow"
    >
      <Ionicons name="sparkles" size={20} color={colors.accent} />
      <View style={styles.stripText}>
        <Text style={[styles.stripTitle, { color: colors.textPrimary }]}>ORA cresce con te</Text>
        <Text style={[styles.stripBody, { color: colors.textSecondary }]}>
          Più aggiorni la tua vita, più ORA ti aiuta nel quotidiano.
        </Text>
      </View>
      <Pressable
        onPress={onUpdate}
        style={({ pressed }) => [
          styles.stripCta,
          { backgroundColor: colors.accent },
          pressed && styles.pressed,
        ]}
        accessibilityRole="button"
        testID="vita-update-cta"
      >
        <Text style={[styles.stripCtaLabel, { color: colors.onAccent }]}>
          Aggiorna qualcosa adesso
        </Text>
      </Pressable>
    </View>
  );
}

/* -------------------------------------------------------------------------- */
/* States                                                                     */
/* -------------------------------------------------------------------------- */

/** ORA has barely met this person yet. One invitation, no placeholder grid. */
export function VitaEmpty({ onTalk }: { onTalk: () => void }) {
  const { colors } = useTheme();
  return (
    <View style={styles.empty} testID="vita-empty">
      <Text style={[styles.emptyTitle, { color: colors.textPrimary }]}>
        ORA sta ancora conoscendo la tua vita.
      </Text>
      <Text style={[styles.emptyBody, { color: colors.textSecondary }]}>
        Puoi raccontarle qualcosa quando vuoi.
      </Text>
      <Pressable
        onPress={onTalk}
        style={({ pressed }) => [
          styles.emptyCta,
          { backgroundColor: colors.accent },
          pressed && styles.pressed,
        ]}
        accessibilityRole="button"
        testID="vita-empty-cta"
      >
        <Text style={[styles.emptyCtaLabel, { color: colors.onAccent }]}>Parla con ORA</Text>
      </Pressable>
    </View>
  );
}

/** Shaped like the page it precedes, so nothing jumps when the real one lands. */
export function VitaSkeleton({ wide }: { wide: boolean }) {
  const { colors } = useTheme();
  const bar = (w: any, h = 12) => (
    <View style={{ width: w, height: h, borderRadius: 6, backgroundColor: colors.skeleton }} />
  );
  const box = (h: number) => (
    <View
      style={[
        styles.skBox,
        { backgroundColor: colors.surface, borderColor: colors.border, minHeight: h },
      ]}
    />
  );
  return (
    <View style={styles.skeleton} testID="vita-skeleton">
      <View style={styles.skHead}>
        {bar(90, 28)}
        {bar('55%')}
      </View>
      <View style={wide ? styles.skRow : undefined}>
        <View style={[styles.skMain, wide && styles.skFlex]}>
          <View style={styles.skTriple}>
            {box(200)}
            {box(200)}
            {box(200)}
          </View>
          <View style={styles.skTriple}>
            {box(130)}
            {box(130)}
            {box(130)}
          </View>
        </View>
        {wide ? (
          <View style={styles.skRail}>
            {box(140)}
            {box(160)}
          </View>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  /*
    Three things now share this row on a phone: the title, the "why" pill and
    the account. At 390px they do not fit on one line, and without a floor the
    title column shrank until "Buongiorno" broke across two lines mid-word.
    The floor makes the row wrap instead — the title keeps the full width and
    the two controls move together to the line below, which is the same
    hierarchy, one line lower. Nothing changes above the phone breakpoint.
  */
  header: {
    flexDirection: 'row', alignItems: 'flex-start',
    gap: tokens.spacing.lg, flexWrap: 'wrap',
  },
  headerText: { flex: 1, gap: 4, minWidth: 240 },
  title: { fontSize: 30, fontWeight: '700', letterSpacing: -0.8, lineHeight: 37 },
  sub: { fontSize: 15, lineHeight: 21, maxWidth: 520 },
  whyBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 7,
    borderWidth: StyleSheet.hairlineWidth, borderRadius: tokens.radius.md,
    paddingHorizontal: tokens.spacing.lg, minHeight: tokens.touch.min,
  },
  whyLabel: { fontSize: 13, fontWeight: '500' },

  scrim: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: tokens.spacing.xl },
  dialog: {
    width: 460, maxWidth: '100%',
    borderRadius: tokens.radius.xl, borderWidth: StyleSheet.hairlineWidth,
    padding: tokens.spacing.xl, gap: tokens.spacing.md,
  },
  dialogHead: { flexDirection: 'row', alignItems: 'flex-start', gap: tokens.spacing.md },
  dialogTitle: { fontSize: 19, fontWeight: '700', flex: 1, letterSpacing: -0.3 },
  close: {
    width: tokens.touch.min, height: tokens.touch.min,
    alignItems: 'center', justifyContent: 'center', marginTop: -10, marginRight: -12,
  },
  dialogLine: { fontSize: 14, lineHeight: 21 },

  strip: {
    flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.lg,
    borderRadius: tokens.radius.lg, borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: tokens.spacing.xl, paddingVertical: tokens.spacing.lg,
    flexWrap: 'wrap',
  },
  stripText: { flex: 1, gap: 2, minWidth: 220 },
  stripTitle: { fontSize: 15, fontWeight: '650' as any },
  stripBody: { fontSize: 13, lineHeight: 19 },
  stripCta: {
    minHeight: tokens.touch.min, justifyContent: 'center',
    paddingHorizontal: tokens.spacing.xl, borderRadius: tokens.radius.md,
  },
  stripCtaLabel: { fontSize: 14, fontWeight: '600' },

  empty: { gap: 8, paddingVertical: tokens.spacing.xxxl, maxWidth: 480 },
  emptyTitle: { fontSize: 22, fontWeight: '700', letterSpacing: -0.5, lineHeight: 29 },
  emptyBody: { fontSize: 15, lineHeight: 22 },
  emptyCta: {
    alignSelf: 'flex-start', minHeight: tokens.touch.min, justifyContent: 'center',
    paddingHorizontal: tokens.spacing.xl, borderRadius: tokens.radius.md,
    marginTop: tokens.spacing.md,
  },
  emptyCtaLabel: { fontSize: 15, fontWeight: '600' },

  skeleton: { gap: tokens.spacing.xl },
  skHead: { gap: tokens.spacing.sm },
  skRow: { flexDirection: 'row', gap: tokens.spacing.xl, alignItems: 'flex-start' },
  skMain: { gap: tokens.spacing.xl },
  skFlex: { flex: 1 },
  skRail: { width: 300, gap: tokens.spacing.lg },
  skTriple: { flexDirection: 'row', gap: tokens.spacing.md },
  skBox: {
    flex: 1,
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
  },
  pressed: { opacity: 0.75 },
});
