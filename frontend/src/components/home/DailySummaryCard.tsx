import { View, Text, StyleSheet, Pressable } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { Ionicons } from '@expo/vector-icons';
import { tokens } from '@/src/theme/tokens';
import { DailySummary } from '@/src/api/client';
import {
  DAILY_WARNING_LABELS, DAILY_OPPORTUNITY_LABELS, ENERGY_LABELS, formatTime,
} from '@/src/utils/labels';

export function DailySummaryCard({ daily, onOpen }: { daily: DailySummary; onOpen: () => void }) {
  const warnings = daily.warnings.slice(0, 2);
  const opps = daily.opportunities.slice(0, 2);
  const firstFree = daily.free_slots.find((f) => f.duration_min >= 30);
  const scoreColor =
    daily.score >= 66 ? tokens.color.success :
    daily.score >= 33 ? tokens.color.warning :
    tokens.color.error;
  const scoreBg =
    daily.score >= 66 ? tokens.color.successBg :
    daily.score >= 33 ? tokens.color.warningBg :
    tokens.color.errorBg;
  return (
    <Animated.View entering={FadeInDown.duration(tokens.motion.slow)} style={styles.card} testID="daily-card">
      <View style={styles.cardHeader}>
        <Text style={styles.h3} accessibilityRole="header">La tua giornata</Text>
        <View style={[styles.scorePill, { backgroundColor: scoreBg }]} accessibilityLabel={`Punteggio ${daily.score} su 100`}>
          <Text style={[styles.scoreText, { color: scoreColor }]}>{daily.score}/100</Text>
        </View>
      </View>
      <View style={styles.metaRow}>
        <DailyMeta icon="calendar-outline" label={`${daily.total_events} eventi`} />
        <DailyMeta icon="time-outline" label={`${Math.round(daily.busy_minutes / 60 * 10) / 10}h occupate`} />
        <DailyMeta icon="battery-half-outline" label={ENERGY_LABELS[daily.energy_estimation.level]} />
      </View>
      {firstFree ? (
        <View style={styles.freeRow}>
          <Ionicons name="sunny-outline" size={13} color={tokens.color.onSurfaceMuted} />
          <Text style={styles.freeText}>
            Prima finestra libera: {formatTime(firstFree.start)}–{formatTime(firstFree.end)}
          </Text>
        </View>
      ) : null}
      {warnings.length > 0 && (
        <View style={styles.chipsRow}>
          {warnings.map((w) => (
            <View
              key={w}
              style={[styles.chip, { backgroundColor: tokens.color.warningBg, borderColor: tokens.color.warning }]}
            >
              <Ionicons name="alert-circle-outline" size={12} color={tokens.color.warning} />
              <Text style={[styles.chipText, { color: tokens.color.warning }]}>
                {DAILY_WARNING_LABELS[w] || w}
              </Text>
            </View>
          ))}
        </View>
      )}
      {opps.length > 0 && (
        <View style={styles.chipsRow}>
          {opps.map((o) => (
            <View
              key={o}
              style={[styles.chip, { backgroundColor: tokens.color.successBg, borderColor: tokens.color.success }]}
            >
              <Ionicons name="leaf-outline" size={12} color={tokens.color.success} />
              <Text style={[styles.chipText, { color: tokens.color.success }]}>
                {DAILY_OPPORTUNITY_LABELS[o] || o}
              </Text>
            </View>
          ))}
        </View>
      )}
      <Pressable
        style={({ pressed }) => [styles.linkBtn, pressed && styles.pressed]}
        onPress={onOpen}
        accessibilityRole="button"
        accessibilityLabel="Vedi il dettaglio della giornata"
        testID="btn-daily-detail"
        hitSlop={8}
      >
        <Text style={styles.linkBtnText}>Vedi giornata</Text>
        <Ionicons name="chevron-forward" size={14} color={tokens.color.onSurface} />
      </Pressable>
    </Animated.View>
  );
}

function DailyMeta({ icon, label }: { icon: any; label: string }) {
  return (
    <View style={styles.dailyMeta} accessible accessibilityLabel={label}>
      <Ionicons name={icon} size={14} color={tokens.color.onSurfaceMuted} />
      <Text style={styles.dailyMetaText}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: tokens.radius.lg,
    padding: tokens.spacing.lg,
    gap: 8,
    borderWidth: 1,
    borderColor: tokens.color.border,
  },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  h3: { fontSize: 16, fontWeight: '600', color: tokens.color.onSurface },
  scorePill: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: tokens.radius.pill },
  scoreText: { fontSize: 12, fontWeight: '700' },
  metaRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 4 },
  dailyMeta: {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    paddingHorizontal: 10, paddingVertical: 5,
    borderRadius: tokens.radius.pill, backgroundColor: tokens.color.surfaceTertiary,
  },
  dailyMetaText: { fontSize: 12, color: tokens.color.onSurface, fontWeight: '500' },
  freeRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 4 },
  freeText: { fontSize: 13, color: tokens.color.onSurfaceMuted },
  chipsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 4 },
  chip: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: 8, paddingVertical: 4,
    borderRadius: tokens.radius.pill, borderWidth: 1,
  },
  chipText: { fontSize: 11, fontWeight: '600' },
  linkBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    alignSelf: 'flex-start', paddingVertical: 8,
    minHeight: tokens.touch.min,
  },
  linkBtnText: { fontSize: 13, color: tokens.color.onSurface, fontWeight: '600' },
  pressed: { opacity: 0.7 },
});
