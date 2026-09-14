/**
 * The call list as a table, on screens wide enough to hold one.
 *
 * The reference mockup laid this out as columns — Data e ora · Numero ·
 * Contatto · Esito · Durata — and columns are genuinely better once there are
 * more than a handful of calls: the eye scans down one field instead of
 * re-reading three lines per row. What does not come across from the mockup
 * is the weight. There it is a B2B dashboard; here it is the same information
 * drawn in ORA's hand — hairline rules instead of boxes, one weight of text,
 * and colour only where a state has earned it.
 *
 * Below the breakpoint this does not shrink: it is replaced. Five columns on
 * a phone means five truncations, and a truncated phone number is worse than
 * no phone number.
 */
import { memo } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { CallCard } from '@/src/api/client';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

import {
  howLong,
  toneColors,
  toneOf,
  whenItHappened,
  whoWasCalled,
} from './callPresentation';

/**
 * The column widths, in flex units.
 *
 * "Contatto" gets the most because a name is the thing you are looking for,
 * and "Esito" gets more than its label needs because the outcome sentence
 * lives under the pill — that sentence is why someone opened the page.
 */
const COL = {
  when: 1.1,
  number: 1.2,
  who: 1.6,
  outcome: 2.2,
  duration: 0.6,
} as const;

type Props = {
  calls: CallCard[];
  onPress: (id: string) => void;
};

function Head() {
  const { colors } = useTheme();
  const label = [styles.head, { color: colors.textTertiary }];
  return (
    <View style={[styles.headRow, { borderBottomColor: colors.divider }]}>
      <Text style={[label, { flex: COL.when }]}>Data e ora</Text>
      <Text style={[label, { flex: COL.number }]}>Numero</Text>
      <Text style={[label, { flex: COL.who }]}>Contatto</Text>
      <Text style={[label, { flex: COL.outcome }]}>Esito</Text>
      <Text style={[label, { flex: COL.duration, textAlign: 'right' }]}>
        Durata
      </Text>
    </View>
  );
}

function Row({ call, onPress }: { call: CallCard; onPress: (id: string) => void }) {
  const { colors } = useTheme();
  const tono = toneOf(call.presentation_status);
  const pill = toneColors(tono, colors);

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${whoWasCalled(call)}. ${call.status_label}. ${call.outcome_summary}`}
      onPress={() => onPress(call.id)}
      testID={`call-row-${call.id}`}
      style={({ pressed, hovered }: any) => [
        styles.row,
        { borderBottomColor: colors.divider },
        (pressed || hovered) && { backgroundColor: colors.backgroundSecondary },
      ]}
    >
      <Text
        numberOfLines={1}
        style={[styles.cell, { flex: COL.when, color: colors.textSecondary }]}
      >
        {whenItHappened(call.started_at || call.created_at)}
      </Text>

      <Text
        numberOfLines={1}
        style={[styles.cell, styles.number, { flex: COL.number, color: colors.textSecondary }]}
      >
        {call.counterparty_number || '—'}
      </Text>

      <Text
        numberOfLines={1}
        style={[styles.cell, styles.who, { flex: COL.who, color: colors.textPrimary }]}
      >
        {whoWasCalled(call)}
      </Text>

      {/* Lo stato e, sotto, la frase che risponde alla domanda per cui
          qualcuno ha aperto questa pagina. Nel mockup l'esito era una sola
          parola in una colonna stretta; la parola da sola non dice se
          l'appuntamento è stato spostato. */}
      <View style={[styles.outcomeCell, { flex: COL.outcome }]}>
        <View style={[styles.pill, { backgroundColor: pill.bg }]}>
          <Text style={[styles.pillText, { color: pill.fg }]}>
            {call.status_label}
          </Text>
        </View>
        <Text
          numberOfLines={1}
          style={[styles.outcome, { color: colors.textSecondary }]}
        >
          {call.outcome_summary}
        </Text>
      </View>

      <Text
        numberOfLines={1}
        style={[
          styles.cell,
          styles.number,
          { flex: COL.duration, color: colors.textTertiary, textAlign: 'right' },
        ]}
      >
        {howLong(call.duration_seconds) || '—'}
      </Text>
    </Pressable>
  );
}

function CallsTableBase({ calls, onPress }: Props) {
  return (
    <View>
      <Head />
      {calls.map((call) => (
        <Row key={call.id} call={call} onPress={onPress} />
      ))}
    </View>
  );
}

export const CallsTable = memo(CallsTableBase);

const styles = StyleSheet.create({
  headRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: tokens.spacing['16'],
    paddingBottom: tokens.spacing['8'],
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  head: { fontSize: 12, fontWeight: '600', letterSpacing: 0.3 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: tokens.spacing['16'],
    paddingVertical: tokens.spacing['12'],
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.sm,
  },
  cell: { fontSize: 14 },
  who: { fontSize: 15, fontWeight: '600', letterSpacing: -0.2 },
  /** Numbers line up only if they are not proportional. */
  number: { fontVariant: ['tabular-nums'] },
  outcomeCell: { gap: 3, minWidth: 0 },
  pill: {
    alignSelf: 'flex-start',
    paddingHorizontal: tokens.spacing['8'],
    paddingVertical: 2,
    borderRadius: tokens.radius.pill,
  },
  pillText: { fontSize: 11, fontWeight: '600', letterSpacing: 0.2 },
  outcome: { fontSize: 13 },
});
