/**
 * Tutte · Completate · Non riuscite · In corso.
 *
 * Four, not eight. The backend knows eight presentation states, and offering
 * all of them would turn a filter into a taxonomy lesson — nobody opens this
 * page thinking "show me the busy ones". These four are the questions people
 * actually arrive with: everything, it worked, it did not, it is happening.
 *
 * "Serve una tua decisione" is deliberately not a chip. Something stopped and
 * waiting for you should not need to be searched for; it belongs in front of
 * you, which is where Updates already puts it.
 */
import { Pressable, ScrollView, StyleSheet, Text } from 'react-native';

import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

/** Empty means every call. The backend filters on presentation state. */
export type CallFilter = '' | 'completata' | 'non_riuscita' | 'in_corso';

const FILTERS: { key: CallFilter; label: string }[] = [
  { key: '', label: 'Tutte' },
  { key: 'completata', label: 'Completate' },
  { key: 'non_riuscita', label: 'Non riuscite' },
  { key: 'in_corso', label: 'In corso' },
];

type Props = {
  value: CallFilter;
  onChange: (next: CallFilter) => void;
};

export function CallFilters({ value, onChange }: Props) {
  const { colors } = useTheme();
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.row}
    >
      {FILTERS.map((f) => {
        const on = f.key === value;
        return (
          <Pressable
            key={f.key || 'all'}
            accessibilityRole="button"
            accessibilityState={{ selected: on }}
            onPress={() => onChange(f.key)}
            testID={`call-filter-${f.key || 'all'}`}
            style={({ pressed }) => [
              styles.chip,
              {
                // La selezione è una superficie piena, non un colore acceso:
                // lo stesso trattamento che il rail dà alla voce corrente.
                backgroundColor: on ? colors.accentMuted : 'transparent',
                borderColor: on ? 'transparent' : colors.border,
              },
              pressed && { opacity: 0.7 },
            ]}
          >
            <Text
              style={[
                styles.label,
                {
                  color: on ? colors.textPrimary : colors.textSecondary,
                  fontWeight: on ? '600' : '500',
                },
              ]}
            >
              {f.label}
            </Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', gap: tokens.spacing['8'], paddingRight: tokens.spacing['16'] },
  chip: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.pill,
    paddingHorizontal: tokens.spacing['12'],
    paddingVertical: 6,
  },
  label: { fontSize: 14 },
});
