/**
 * One call, in the list.
 *
 * Three lines, in the order a person reads them: who was called, when and for
 * how long, and how it went. The state sits at the end of the first line
 * rather than in a column of its own — a column would make this a table, and
 * a table is what a call centre looks at, not what someone checks after
 * asking a favour.
 *
 * The mockup this came from put the outcome in a narrow "Esito" column and the
 * reason nowhere. That is backwards: the reason is why the call exists, and
 * the outcome is the answer to the question that made someone open the screen.
 * Both get a full line here.
 */
import { memo } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { CallCard } from '@/src/api/client';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

import {
  toneColors,
  toneOf,
  whenAndHowLong,
  whoWasCalled,
} from './callPresentation';

type Props = {
  call: CallCard;
  onPress: (id: string) => void;
};

function CallRowBase({ call, onPress }: Props) {
  const { colors } = useTheme();
  const tono = toneOf(call.presentation_status);
  const pill = toneColors(tono, colors);
  const chiedeQualcosa = tono === 'attention';

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${whoWasCalled(call)}. ${call.status_label}. ${call.outcome_summary}`}
      onPress={() => onPress(call.id)}
      style={({ pressed }) => [
        styles.row,
        {
          backgroundColor: colors.surface,
          borderColor: chiedeQualcosa ? colors.warning : colors.border,
          // Un bordo appena più deciso, non un colore acceso: quello che
          // chiede una decisione si nota, non grida.
          borderLeftWidth: chiedeQualcosa ? 3 : StyleSheet.hairlineWidth,
        },
        pressed && { opacity: 0.7 },
      ]}
    >
      <View style={styles.head}>
        <Text
          numberOfLines={1}
          style={[styles.who, { color: colors.textPrimary }]}
        >
          {whoWasCalled(call)}
        </Text>
        <View style={[styles.pill, { backgroundColor: pill.bg }]}>
          <Text style={[styles.pillText, { color: pill.fg }]}>
            {call.status_label}
          </Text>
        </View>
      </View>

      <Text style={[styles.when, { color: colors.textTertiary }]}>
        {whenAndHowLong(call)}
      </Text>

      <Text
        numberOfLines={2}
        style={[
          styles.outcome,
          { color: chiedeQualcosa ? colors.textPrimary : colors.textSecondary },
        ]}
      >
        {call.outcome_summary}
      </Text>
    </Pressable>
  );
}

export const CallRow = memo(CallRowBase);

const styles = StyleSheet.create({
  row: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.lg,
    paddingVertical: tokens.spacing['16'],
    paddingHorizontal: tokens.spacing['16'],
    gap: tokens.spacing['4'],
  },
  head: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: tokens.spacing['8'],
  },
  who: { flex: 1, fontSize: 16, fontWeight: '600', letterSpacing: -0.2 },
  pill: {
    paddingHorizontal: tokens.spacing['8'],
    paddingVertical: 3,
    borderRadius: tokens.radius.pill,
  },
  pillText: { fontSize: 11, fontWeight: '600', letterSpacing: 0.2 },
  when: { fontSize: 13 },
  outcome: { fontSize: 14, lineHeight: 20, marginTop: tokens.spacing['4'] },
});
