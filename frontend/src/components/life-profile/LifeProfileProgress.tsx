/**
 * How much of a life ORA understands — said quietly.
 *
 * The number is the one thing on this screen a person will read literally, so
 * the copy says what it actually measures: not how much of a form is filled
 * in, but how much of what would help ORA already knows. That distinction is
 * the whole reason the figure is allowed to exist.
 *
 * Deliberately not a game. No streak, no badge, no "manca poco!", no confetti
 * at a threshold. A bar, a percentage, and the areas underneath it — someone
 * who stops at 30% has a working assistant, and nothing here should suggest
 * otherwise.
 */
import { memo } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { LifeAreaCompleteness } from '@/src/api/client';
import { areaIconName } from '@/src/components/life-profile/areaIcon';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

export type LifeProfileProgressProps = {
  percent: number;
  areas: LifeAreaCompleteness[];
  /** The area being worked on now, if any. */
  activeAreaId?: string | null;
  /** Tapping an area is optional: Vita offers it, the first run does not. */
  onOpenArea?: (areaId: string) => void;
  compact?: boolean;
  testID?: string;
};

/** A person reads a bar before they read a number; both have to agree. */
function Bar({ percent, color, track }: { percent: number; color: string; track: string }) {
  const width = `${Math.max(0, Math.min(100, percent))}%` as const;
  return (
    <View style={[styles.track, { backgroundColor: track }]}>
      <View style={[styles.fill, { width, backgroundColor: color }]} />
    </View>
  );
}

export const LifeProfileProgress = memo(function LifeProfileProgress({
  percent,
  areas,
  activeAreaId,
  onOpenArea,
  compact = false,
  testID = 'life-profile-progress',
}: LifeProfileProgressProps) {
  const { colors } = useTheme();
  const visible = areas.filter((a) => a.state !== 'not_applicable');

  return (
    <View
      style={[styles.root, { borderColor: colors.border, backgroundColor: colors.surface }]}
      testID={testID}
    >
      <View style={styles.head}>
        <Text style={[styles.title, { color: colors.textSecondary }]}>Profilo vita</Text>
        <Text
          style={[styles.percent, { color: colors.textPrimary }]}
          testID={`${testID}-percent`}
          accessibilityLabel={`ORA conosce il ${percent} per cento di quello che può aiutarla`}
        >
          {percent}%
        </Text>
      </View>

      <Bar percent={percent} color={colors.accent} track={colors.divider} />

      {/*
        Said once, plainly. "Profilo incompleto" would read as an error, and
        there is nothing wrong with a person who has told ORA very little.
      */}
      <Text style={[styles.caption, { color: colors.textTertiary }]}>
        Quanto ORA conosce di ciò che può aiutarti. Puoi completarlo nel tempo.
      </Text>

      {compact ? null : (
        <View style={styles.areas} testID={`${testID}-areas`}>
          {visible.map((a) => {
            const active = a.area_id === activeAreaId;
            const row = (
              <View
                style={[
                  styles.area,
                  { borderColor: active ? colors.accent : colors.border },
                  active && { backgroundColor: colors.surfaceElevated },
                ]}
              >
                <View style={styles.areaHead}>
                  <View
                    style={[
                      styles.areaTile,
                      { backgroundColor: active ? colors.accent : colors.surfaceElevated },
                    ]}
                  >
                    <Ionicons
                      name={areaIconName(a.icon_key)}
                      size={14}
                      color={active ? colors.onAccent : colors.textTertiary}
                    />
                  </View>
                  <Text
                    style={[styles.areaTitle, { color: colors.textPrimary }]}
                    numberOfLines={1}
                  >
                    {a.title}
                  </Text>
                  <Text style={[styles.areaPercent, { color: colors.textTertiary }]}>
                    {a.percent}%
                  </Text>
                </View>
                <Bar
                  percent={a.percent}
                  color={active ? colors.accent : colors.textTertiary}
                  track={colors.divider}
                />
                <Text style={[styles.areaState, { color: colors.textTertiary }]} numberOfLines={1}>
                  {a.state_label}
                </Text>
              </View>
            );
            return onOpenArea ? (
              <Pressable
                key={a.area_id}
                onPress={() => onOpenArea(a.area_id)}
                accessibilityRole="button"
                accessibilityLabel={`${a.title}, ${a.percent} per cento. ${a.state_label}`}
                testID={`${testID}-area-${a.area_id}`}
                style={styles.areaPress}
              >
                {row}
              </Pressable>
            ) : (
              <View key={a.area_id} testID={`${testID}-area-${a.area_id}`} style={styles.areaPress}>
                {row}
              </View>
            );
          })}
        </View>
      )}
    </View>
  );
});

const styles = StyleSheet.create({
  root: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.lg,
    padding: tokens.spacing.md,
    gap: tokens.spacing.xs,
  },
  head: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between' },
  title: { fontSize: 12, letterSpacing: 0.4, textTransform: 'uppercase' },
  percent: { fontSize: 20, fontWeight: '600' },
  track: { height: 4, borderRadius: 2, overflow: 'hidden' },
  fill: { height: '100%', borderRadius: 2 },
  caption: { fontSize: 12, lineHeight: 17 },
  areas: { marginTop: tokens.spacing.sm, gap: tokens.spacing.sm },
  // 44 is the smallest thing a thumb finds reliably; the row is taller anyway,
  // and saying so keeps it that way if the content ever shrinks.
  areaPress: { minHeight: 44 },
  area: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.md,
    padding: tokens.spacing.sm,
    gap: 6,
  },
  areaHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  areaTile: {
    width: 24,
    height: 24,
    borderRadius: tokens.radius.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  areaTitle: { fontSize: 14, fontWeight: '500', flex: 1 },
  areaPercent: { fontSize: 12, fontVariant: ['tabular-nums'] },
  areaState: { fontSize: 11 },
});
