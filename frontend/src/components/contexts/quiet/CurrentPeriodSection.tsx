import { StyleSheet, View } from 'react-native';
import { SectionHeader } from '@/src/components/ui/SectionHeader';
import { tokens } from '@/src/theme/tokens';
import type { LiveSituationRow as LiveSituationModel } from './buildContextsMap';
import { LiveSituationRow } from './LiveSituationRow';

type Props = {
  situations: LiveSituationModel[];
  onOpen: (href: string) => void;
};

/** Live situations only — never Home priorities. Hidden when empty. */
export function CurrentPeriodSection({ situations, onOpen }: Props) {
  if (!situations.length) return null;

  return (
    <View style={styles.wrap} testID="contesti-current-period">
      <SectionHeader title="In questo periodo" />
      <View style={styles.list}>
        {situations.map((s) => (
          <LiveSituationRow
            key={s.id}
            situation={s}
            onPress={s.href ? () => onOpen(s.href!) : undefined}
          />
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginBottom: tokens.spacing.xxl },
  list: { gap: 0 },
});
