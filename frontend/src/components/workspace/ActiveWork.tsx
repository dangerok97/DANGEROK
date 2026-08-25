import * as React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { GenerativeObjectRenderer } from '@/src/components/generative/GenerativeObjectRenderer';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

/**
 * The active work surface.
 *
 * This is the centre of the Workspace, not one card among several: the object
 * ORA has prepared gets the full width of the main column and no competing
 * chrome. The renderer itself is untouched — it receives exactly the props it
 * always received, so every interaction, block type and focus event keeps
 * working. What changed is how much room it is given.
 */
export function ActiveWork({
  title,
  purpose,
  content,
  objectId,
  onInteract,
  onAskOra,
}: {
  title: string;
  purpose?: string | null;
  content: any;
  objectId: string;
  onInteract: (eventType: string, payload: Record<string, unknown>) => void;
  onAskOra: () => void;
}) {
  const { colors } = useTheme();

  return (
    <View
      style={[styles.surface, { backgroundColor: colors.surface, borderColor: colors.border }]}
      testID="workspace-active-work"
    >
      <View style={styles.head}>
        <Text
          style={[styles.title, { color: colors.textPrimary }]}
          accessibilityRole="header"
          aria-level={2}
        >
          {title}
        </Text>
        {purpose ? (
          <Text style={[styles.purpose, { color: colors.textSecondary }]}>{purpose}</Text>
        ) : null}
      </View>

      {/*
        No inner card. The renderer draws its own blocks; wrapping them in a
        second bordered box would frame the work twice and shrink it.
      */}
      <View style={styles.canvas}>
        <GenerativeObjectRenderer content={content} objectId={objectId} onInteract={onInteract} />
      </View>

      <Pressable
        onPress={onAskOra}
        style={({ pressed }) => [styles.ask, { borderColor: colors.border }, pressed && styles.pressed]}
        accessibilityRole="button"
        testID="workspace-ask-ora-object"
      >
        <Ionicons name="chatbubble-ellipses-outline" size={15} color={colors.accent} />
        <Text style={[styles.askLabel, { color: colors.textSecondary }]}>
          Chiedi a ORA su questo
        </Text>
      </Pressable>
    </View>
  );
}

/**
 * A plan that has produced nothing yet.
 *
 * Deliberately small. An empty state sized like a real work surface would
 * announce absence louder than the step the user should actually take.
 */
export function NoWorkYet() {
  const { colors } = useTheme();
  return (
    <View
      style={[styles.empty, { backgroundColor: colors.surface, borderColor: colors.border }]}
      testID="workspace-no-work"
    >
      <Text style={[styles.emptyText, { color: colors.textSecondary }]}>
        ORA non ha ancora preparato materiale per questo obiettivo. Comparirà qui appena c'è
        qualcosa su cui lavorare.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  surface: {
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    padding: tokens.spacing.xl,
    gap: tokens.spacing.lg,
  },
  head: { gap: 4 },
  title: { fontSize: 20, fontWeight: '650' as any, lineHeight: 27, letterSpacing: -0.3 },
  purpose: { fontSize: 14, lineHeight: 20 },
  canvas: { gap: tokens.spacing.md },
  ask: {
    flexDirection: 'row', alignItems: 'center', gap: 8, alignSelf: 'flex-start',
    minHeight: tokens.touch.min, paddingHorizontal: tokens.spacing.lg,
    borderRadius: tokens.radius.md, borderWidth: StyleSheet.hairlineWidth,
  },
  askLabel: { fontSize: 13, fontWeight: '500' },
  empty: {
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    padding: tokens.spacing.xl,
  },
  emptyText: { fontSize: 14, lineHeight: 21 },
  pressed: { opacity: 0.7 },
});
