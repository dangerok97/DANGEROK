import { useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import type { HomeCurrentSituation, HomeItem } from '@/src/api/client';

const WEEKDAYS = ['LUN', 'MAR', 'MER', 'GIO', 'VEN', 'SAB', 'DOM'];

function startOfMonth(d: Date) { return new Date(d.getFullYear(), d.getMonth(), 1); }
function isSameDay(a: Date, b: Date) { return a.toDateString() === b.toDateString(); }

function itemDate(i: HomeItem): Date | null {
  const raw = i.start_at || i.due_at || i.goal_target_date;
  if (!raw) return null;
  const d = new Date(raw);
  return Number.isNaN(d.getTime()) ? null : d;
}

/**
 * The contextual rail — what is around the decision, not the decision itself.
 *
 * Everything here is derived from the Home payload the page already loaded:
 * no extra fetch, no second source of truth. The month grid is a real calendar
 * of the user's own items — a day is marked because something of theirs falls
 * on it, never to make the grid look populated. If no items carry dates, the
 * marks simply do not appear.
 */
export function ContextRail({
  items,
  situation,
  questionCount,
  onOpenItem,
  onSeeAll,
}: {
  items: HomeItem[];
  situation?: HomeCurrentSituation | null;
  questionCount: number;
  onOpenItem: (item: HomeItem) => void;
  onSeeAll?: () => void;
}) {
  const { colors } = useTheme();
  const today = useMemo(() => new Date(), []);
  const [cursor, setCursor] = useState(() => startOfMonth(new Date()));
  /*
    Which day the panel below is describing. Null means "no day chosen", and
    the panel falls back to what is coming up next — the calendar is a way in,
    not a mode you have to leave.
  */
  const [selected, setSelected] = useState<Date | null>(null);

  const dated = useMemo(
    () => items.map((i) => ({ item: i, at: itemDate(i) })).filter((x) => !!x.at) as { item: HomeItem; at: Date }[],
    [items],
  );

  /*
    Impegni grouped by calendar day, derived from the items Home already
    loaded. No request is made when a day is tapped: the events for the period
    are in memory, so selecting a day is a lookup, not a round trip.
  */
  const byDay = useMemo(() => {
    const map = new Map<string, { item: HomeItem; at: Date }[]>();
    for (const entry of dated) {
      const k = entry.at.toDateString();
      const list = map.get(k) || [];
      list.push(entry);
      map.set(k, list);
    }
    for (const list of map.values()) list.sort((a, b) => a.at.getTime() - b.at.getTime());
    return map;
  }, [dated]);

  const selectedEntries = useMemo(
    () => (selected ? byDay.get(selected.toDateString()) || [] : []),
    [selected, byDay],
  );

  const markedDays = useMemo(() => {
    const set = new Set<string>();
    for (const { at } of dated) {
      if (at.getFullYear() === cursor.getFullYear() && at.getMonth() === cursor.getMonth()) {
        set.add(String(at.getDate()));
      }
    }
    return set;
  }, [dated, cursor]);

  const upcoming = useMemo(
    () =>
      dated
        .filter((x) => x.at.getTime() >= new Date().setHours(0, 0, 0, 0))
        .sort((a, b) => a.at.getTime() - b.at.getTime())
        .slice(0, 3),
    [dated],
  );

  /** Leading blanks so the 1st lands under its weekday (Monday-first). */
  const grid = useMemo(() => {
    const first = startOfMonth(cursor);
    const lead = (first.getDay() + 6) % 7;
    const days = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0).getDate();
    const cells: (number | null)[] = Array(lead).fill(null);
    for (let d = 1; d <= days; d++) cells.push(d);
    while (cells.length % 7 !== 0) cells.push(null);
    return cells;
  }, [cursor]);

  const shiftMonth = (delta: number) =>
    setCursor((c) => new Date(c.getFullYear(), c.getMonth() + delta, 1));

  const summary = [
    { icon: 'radio-button-on-outline' as const, label: 'Situazioni attive', value: situation?.indicators?.length ?? 0 },
    { icon: 'help-circle-outline' as const, label: 'Domande in attesa', value: questionCount },
    { icon: 'notifications-outline' as const, label: 'Azioni in sospeso', value: situation?.open_actions_count ?? 0 },
  ].filter((s) => s.value > 0);

  return (
    <View style={styles.rail} testID="home-context-rail">
      {/* Calendar */}
      <View style={[styles.panel, { backgroundColor: colors.surface, borderColor: colors.border }]}>
        <View style={styles.panelHead}>
          <Ionicons name="calendar-outline" size={13} color={colors.textSecondary} />
          <Text style={[styles.panelTitle, { color: colors.textSecondary }]}>CALENDARIO</Text>
          <View style={styles.monthNav}>
            <Pressable onPress={() => shiftMonth(-1)} hitSlop={8} accessibilityRole="button" accessibilityLabel="Mese precedente">
              <Ionicons name="chevron-back" size={15} color={colors.textTertiary} />
            </Pressable>
            <Pressable
              onPress={() => { const n = new Date(); setCursor(startOfMonth(n)); setSelected(n); }}
              hitSlop={8}
              accessibilityRole="button"
              testID="rail-today"
            >
              <Text style={[styles.todayBtn, { color: colors.textSecondary }]}>Oggi</Text>
            </Pressable>
            <Pressable onPress={() => shiftMonth(1)} hitSlop={8} accessibilityRole="button" accessibilityLabel="Mese successivo">
              <Ionicons name="chevron-forward" size={15} color={colors.textTertiary} />
            </Pressable>
          </View>
        </View>

        <Text style={[styles.monthLabel, { color: colors.textPrimary }]}>
          {cursor.toLocaleDateString('it-IT', { month: 'long', year: 'numeric' })}
        </Text>

        <View style={styles.week}>
          {WEEKDAYS.map((w) => (
            <Text key={w} style={[styles.weekday, { color: colors.textTertiary }]}>{w}</Text>
          ))}
        </View>

        <View style={styles.grid}>
          {grid.map((day, idx) => {
            if (day === null) return <View key={`b${idx}`} style={styles.cell} />;
            const cellDate = new Date(cursor.getFullYear(), cursor.getMonth(), day);
            const isToday = isSameDay(cellDate, today);
            const isSelected = !!selected && isSameDay(cellDate, selected);
            const marked = markedDays.has(String(day));
            const count = byDay.get(cellDate.toDateString())?.length || 0;
            return (
              <Pressable
                key={`d${day}`}
                style={styles.cell}
                onPress={() => setSelected(isSelected ? null : cellDate)}
                accessibilityRole="button"
                accessibilityState={{ selected: isSelected }}
                accessibilityLabel={
                  count
                    ? `${day} ${cursor.toLocaleDateString('it-IT', { month: 'long' })}, ${count} impegn${count === 1 ? 'o' : 'i'}`
                    : `${day} ${cursor.toLocaleDateString('it-IT', { month: 'long' })}, nessun impegno`
                }
                testID={`rail-day-${day}`}
              >
                {/*
                  Three states, told apart without relying on colour alone:
                  today is filled, the chosen day is ringed, and a day with
                  something on it carries a dot underneath.
                */}
                <View
                  style={[
                    styles.dayWrap,
                    isToday && { backgroundColor: colors.accent },
                    isSelected && !isToday && {
                      borderWidth: 1.5,
                      borderColor: colors.accent,
                    },
                    isSelected && isToday && { borderWidth: 1.5, borderColor: colors.textPrimary },
                  ]}
                >
                  <Text
                    style={[
                      styles.dayText,
                      { color: isToday ? colors.onAccent : colors.textPrimary },
                      isSelected && !isToday && { fontWeight: '700' },
                    ]}
                  >
                    {day}
                  </Text>
                </View>
                {marked && !isToday ? (
                  <View style={[styles.dot, { backgroundColor: colors.warning }]} />
                ) : (
                  <View style={styles.dotSpacer} />
                )}
              </Pressable>
            );
          })}
        </View>
      </View>

      {/*
        One panel, two questions. With a day chosen it answers "what do I have
        on the 27th"; with none it answers "what is coming". Swapping the
        contents rather than adding a second panel keeps the rail from growing
        a new block every time you tap something.
      */}
      {selected ? (
        <View style={[styles.panel, { backgroundColor: colors.surface, borderColor: colors.border }]} testID="rail-day-agenda">
          <View style={styles.panelHead}>
            <Text style={[styles.panelTitle, { color: colors.textSecondary }]}>
              {`IMPEGNI DEL ${selected.getDate()} ${selected
                .toLocaleDateString('it-IT', { month: 'long' })
                .toUpperCase()}`}
            </Text>
            <Pressable
              onPress={() => setSelected(null)}
              hitSlop={8}
              style={styles.closeDay}
              accessibilityRole="button"
              accessibilityLabel="Chiudi il giorno selezionato"
              testID="rail-day-clear"
            >
              <Ionicons name="close" size={14} color={colors.textTertiary} />
            </Pressable>
          </View>

          {selectedEntries.length ? (
            selectedEntries.map(({ item, at }) => (
              <Pressable
                key={item.id}
                onPress={() => onOpenItem(item)}
                style={({ pressed }) => [styles.upRow, pressed && styles.pressed]}
                accessibilityRole="button"
                testID={`rail-day-item-${item.id}`}
              >
                <Text style={[styles.dayTime, { color: colors.textSecondary }]}>
                  {at.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })}
                </Text>
                <View style={styles.upText}>
                  <Text style={[styles.upTitle, { color: colors.textPrimary }]} numberOfLines={1}>
                    {item.title}
                  </Text>
                  {item.location || item.subtitle ? (
                    <Text style={[styles.upMeta, { color: colors.textTertiary }]} numberOfLines={1}>
                      {item.location || item.subtitle}
                    </Text>
                  ) : null}
                </View>
              </Pressable>
            ))
          ) : (
            <Text style={[styles.emptyDay, { color: colors.textTertiary }]} testID="rail-day-empty">
              Nessun impegno per questa giornata.
            </Text>
          )}
        </View>
      ) : upcoming.length ? (
        <View style={[styles.panel, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <Text style={[styles.panelTitle, { color: colors.textSecondary }]}>PROSSIMI APPUNTAMENTI</Text>
          {upcoming.map(({ item, at }) => (
            <Pressable
              key={item.id}
              onPress={() => onOpenItem(item)}
              style={({ pressed }) => [styles.upRow, pressed && styles.pressed]}
              accessibilityRole="button"
              testID={`rail-upcoming-${item.id}`}
            >
              <View style={styles.upDate}>
                <Text style={[styles.upDay, { color: colors.textPrimary }]}>{at.getDate()}</Text>
                <Text style={[styles.upMonth, { color: colors.textTertiary }]}>
                  {at.toLocaleDateString('it-IT', { month: 'short' }).replace('.', '').toUpperCase()}
                </Text>
              </View>
              <View style={styles.upText}>
                <Text style={[styles.upTitle, { color: colors.textPrimary }]} numberOfLines={1}>
                  {item.title}
                </Text>
                {item.location || item.subtitle ? (
                  <Text style={[styles.upMeta, { color: colors.textTertiary }]} numberOfLines={1}>
                    {item.location || item.subtitle}
                  </Text>
                ) : null}
              </View>
            </Pressable>
          ))}
          {onSeeAll ? (
            <Pressable onPress={onSeeAll} style={({ pressed }) => [styles.footer, pressed && styles.pressed]} accessibilityRole="button">
              <Text style={[styles.footerLabel, { color: colors.accent }]}>Vedi tutti</Text>
              <Ionicons name="arrow-forward" size={12} color={colors.accent} />
            </Pressable>
          ) : null}
        </View>
      ) : null}

      {/* Summary — counts only, never scores */}
      {summary.length ? (
        <View style={[styles.panel, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <Text style={[styles.panelTitle, { color: colors.textSecondary }]}>ORA IN SINTESI</Text>
          {summary.map((s) => (
            <View key={s.label} style={styles.sumRow}>
              <Ionicons name={s.icon} size={17} color={colors.accent} />
              <Text style={[styles.sumLabel, { color: colors.textSecondary }]}>{s.label}</Text>
              <Text style={[styles.sumValue, { color: colors.textPrimary }]}>{s.value}</Text>
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  rail: { gap: tokens.spacing.lg },
  panel: {
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    padding: tokens.spacing.lg,
    gap: tokens.spacing.sm,
  },
  panelHead: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  panelTitle: { fontSize: 11, fontWeight: '700', letterSpacing: 1 },
  monthNav: { flexDirection: 'row', alignItems: 'center', gap: 8, marginLeft: 'auto' },
  todayBtn: { fontSize: 12, fontWeight: '500' },
  monthLabel: {
    fontSize: 16,
    fontWeight: '700',
    letterSpacing: -0.2,
    textTransform: 'capitalize',
    marginTop: 2,
  },
  week: { flexDirection: 'row', marginTop: 4 },
  weekday: { flex: 1, textAlign: 'center', fontSize: 9, fontWeight: '700', letterSpacing: 0.4 },
  grid: { flexDirection: 'row', flexWrap: 'wrap' },
  cell: { width: `${100 / 7}%`, alignItems: 'center', paddingVertical: 2 },
  dayWrap: {
    width: 26,
    height: 26,
    borderRadius: 13,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dayText: { fontSize: 12 },
  dot: { width: 3, height: 3, borderRadius: 1.5, marginTop: 1 },
  dotSpacer: { width: 3, height: 3, marginTop: 1 },
  upRow: { flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.md, minHeight: 44 },
  dayTime: { width: 46, fontSize: 12, fontWeight: '600' },
  closeDay: { marginLeft: 'auto', padding: 2 },
  emptyDay: { fontSize: 13, lineHeight: 19, paddingVertical: 6 },
  upDate: { width: 34, alignItems: 'center' },
  upDay: { fontSize: 15, fontWeight: '700', lineHeight: 18 },
  upMonth: { fontSize: 9, fontWeight: '600', letterSpacing: 0.4 },
  upText: { flex: 1, gap: 1 },
  upTitle: { fontSize: 13, fontWeight: '600' },
  upMeta: { fontSize: 11 },
  sumRow: { flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.md, minHeight: 40 },
  sumLabel: { flex: 1, fontSize: 13 },
  sumValue: { fontSize: 17, fontWeight: '700' },
  footer: { flexDirection: 'row', alignItems: 'center', gap: 5, minHeight: 30 },
  footerLabel: { fontSize: 12, fontWeight: '600' },
  pressed: { opacity: 0.65 },
});
