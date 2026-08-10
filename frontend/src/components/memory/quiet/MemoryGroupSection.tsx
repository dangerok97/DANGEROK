import { StyleSheet, Text, View } from 'react-native';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { MemoryRow } from './MemoryRow';
import type { MemoryGroupView, MemoryRow as MemoryRowModel } from './mapFromMemoryApi';

type Props = {
  group: MemoryGroupView;
  onClarify?: (item: MemoryRowModel) => void;
};

export function MemoryGroupSection({ group, onClarify }: Props) {
  const { colors } = useTheme();
  if (!group.items.length) return null;
  return (
    <View style={styles.wrap} testID={`memory-group-${group.domain || group.id}`}>
      <Text style={[styles.label, { color: colors.textTertiary }]}>{group.label}</Text>
      <View>
        {group.items.map((item, idx) => (
          <MemoryRow
            key={item.id}
            item={item}
            showDivider={idx < group.items.length - 1}
            onClarify={onClarify}
          />
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    marginBottom: tokens.spacing.xl,
  },
  label: {
    fontSize: tokens.typography.caption.fontSize,
    lineHeight: tokens.typography.caption.lineHeight,
    letterSpacing: 0.4,
    textTransform: 'uppercase',
    marginBottom: tokens.spacing.xs,
  },
});
