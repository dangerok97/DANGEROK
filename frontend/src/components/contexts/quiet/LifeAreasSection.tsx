import { StyleSheet, View } from 'react-native';
import { SectionHeader } from '@/src/components/ui/SectionHeader';
import { tokens } from '@/src/theme/tokens';
import type { LifeAreaRow } from './buildContextsMap';
import { ContextRow } from './ContextRow';

type Props = {
  areas: LifeAreaRow[];
};

/** Persistent known life areas — hidden when empty. No fake detail nav. */
export function LifeAreasSection({ areas }: Props) {
  if (!areas.length) return null;

  return (
    <View style={styles.wrap} testID="contesti-life-areas">
      <SectionHeader title="La tua vita" />
      <View>
        {areas.map((area, i) => (
          <ContextRow
            key={area.id}
            area={area}
            showDivider={i < areas.length - 1}
          />
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginBottom: tokens.spacing.xxl },
});
