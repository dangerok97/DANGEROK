import * as React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

/**
 * Loading, shaped like the Workspace it precedes — header, current step, work
 * surface. A spinner in the middle of an empty page tells the user nothing
 * about what is arriving; this tells them the shape of it.
 */
export function WorkspaceSkeleton({ wide }: { wide: boolean }) {
  const { colors } = useTheme();
  const bar = (w: any, h = 12) => (
    <View style={{ width: w, height: h, borderRadius: 6, backgroundColor: colors.skeleton }} />
  );
  const panel = (children: React.ReactNode, minHeight?: number) => (
    <View
      style={[
        styles.panel,
        { backgroundColor: colors.surface, borderColor: colors.border },
        minHeight ? { minHeight } : null,
      ]}
    >
      {children}
    </View>
  );

  return (
    <View style={styles.wrap} testID="workspace-skeleton">
      <View style={styles.headBlock}>
        {bar(70, 10)}
        {bar('60%', 24)}
        {bar('40%')}
      </View>
      <View style={wide ? styles.row : undefined}>
        <View style={[styles.main, wide && styles.mainWide]}>
          {panel(
            <>
              {bar(56, 10)}
              {bar('70%', 18)}
              {bar(150, 40)}
            </>,
          )}
          {panel(
            <>
              {bar('50%', 16)}
              {bar('90%')}
              {bar('80%')}
              {bar('85%')}
            </>,
            260,
          )}
        </View>
        {wide ? (
          <View style={styles.rail}>
            {panel(
              <>
                {bar(80, 10)}
                {bar('90%')}
                {bar('75%')}
              </>,
            )}
          </View>
        ) : null}
      </View>
    </View>
  );
}

/** Something went wrong — said as a sentence, with a way out of it. */
export function WorkspaceError({
  message,
  onRetry,
  onBack,
}: {
  message?: string | null;
  onRetry: () => void;
  onBack: () => void;
}) {
  const { colors } = useTheme();
  return (
    <View
      style={[styles.error, { backgroundColor: colors.surface, borderColor: colors.border }]}
      testID="workspace-error"
    >
      <Text style={[styles.errorTitle, { color: colors.textPrimary }]}>
        Non riesco ad aprire questo obiettivo.
      </Text>
      <Text style={[styles.errorBody, { color: colors.textSecondary }]}>
        {message || 'Riprova tra un momento: il lavoro che hai fatto non è andato perso.'}
      </Text>
      <View style={styles.errorActions}>
        <Pressable
          onPress={onRetry}
          style={({ pressed }) => [
            styles.primary,
            { backgroundColor: colors.accent },
            pressed && styles.pressed,
          ]}
          accessibilityRole="button"
          testID="workspace-error-retry"
        >
          <Text style={[styles.primaryLabel, { color: colors.onAccent }]}>Riprova</Text>
        </Pressable>
        <Pressable
          onPress={onBack}
          style={({ pressed }) => [styles.ghost, { borderColor: colors.border }, pressed && styles.pressed]}
          accessibilityRole="button"
        >
          <Text style={[styles.ghostLabel, { color: colors.textPrimary }]}>Torna indietro</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: tokens.spacing.xl },
  headBlock: { gap: tokens.spacing.sm },
  row: { flexDirection: 'row', gap: tokens.spacing.xl, alignItems: 'flex-start' },
  main: { gap: tokens.spacing.lg },
  mainWide: { flex: 1 },
  rail: { width: 300, gap: tokens.spacing.lg },
  panel: {
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    padding: tokens.spacing.lg,
    gap: tokens.spacing.md,
  },
  error: {
    // Held to the width of the work column: a full-bleed box around two lines
    // of text reads as a page-wide failure rather than a small one.
    maxWidth: 760,
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    padding: tokens.spacing.xxl,
    gap: tokens.spacing.sm,
  },
  errorTitle: { fontSize: 18, fontWeight: '600', lineHeight: 25 },
  errorBody: { fontSize: 14, lineHeight: 21 },
  errorActions: { flexDirection: 'row', gap: tokens.spacing.md, marginTop: tokens.spacing.md },
  primary: {
    minHeight: tokens.touch.min, justifyContent: 'center',
    paddingHorizontal: tokens.spacing.xl, borderRadius: tokens.radius.md,
  },
  primaryLabel: { fontSize: 15, fontWeight: '600' },
  ghost: {
    minHeight: tokens.touch.min, justifyContent: 'center',
    paddingHorizontal: tokens.spacing.xl, borderRadius: tokens.radius.md,
    borderWidth: StyleSheet.hairlineWidth,
  },
  ghostLabel: { fontSize: 14, fontWeight: '600' },
  pressed: { opacity: 0.75 },
});
