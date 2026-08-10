import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import type { MemoryRow as MemoryRowModel } from './mapFromMemoryApi';

type Props = {
  item: MemoryRowModel;
  showDivider?: boolean;
  onClarify?: (item: MemoryRowModel) => void;
};

function statusHint(status: string, clarifiable?: boolean): string | null {
  if (status === 'likely') return 'Probabile';
  if (status === 'ambiguous') return clarifiable ? 'Da chiarire' : 'Da chiarire';
  return null;
}

export function MemoryRow({ item, showDivider, onClarify }: Props) {
  const { colors } = useTheme();
  const [open, setOpen] = useState(false);
  const hint = statusHint(item.status, item.clarifiable);
  const hasProv = !!(item.provenanceLabel || '').trim();
  const canClarify = item.clarifiable && typeof onClarify === 'function';

  const onPressHint = () => {
    if (canClarify) {
      onClarify!(item);
      return;
    }
    if (hasProv) setOpen((v) => !v);
  };

  return (
    <View>
      <View style={styles.row}>
        <Pressable
          onPress={hasProv && !canClarify ? () => setOpen((v) => !v) : undefined}
          disabled={!hasProv || canClarify}
          style={styles.textCol}
          accessibilityRole="text"
          accessibilityLabel={item.statement}
          testID={`memory-row-${item.id}`}
        >
          <Text style={[styles.statement, { color: colors.textPrimary }]}>
            {item.statement}
          </Text>
          {open && hasProv ? (
            <Text style={[styles.prov, { color: colors.textSecondary }]}>
              {item.provenanceLabel}
            </Text>
          ) : null}
        </Pressable>
        {hint ? (
          <Pressable
            onPress={onPressHint}
            style={({ pressed }) => [
              styles.hintHit,
              pressed && canClarify && { opacity: 0.65 },
            ]}
            accessibilityRole={canClarify ? 'button' : 'text'}
            accessibilityLabel={
              canClarify ? 'Chiarisci questo ricordo con ORA' : hint
            }
            testID={
              canClarify
                ? `memory-clarify-${item.id}`
                : `memory-hint-${item.id}`
            }
          >
            <Text
              style={[
                styles.hint,
                {
                  color: canClarify ? colors.textPrimary : colors.textTertiary,
                  textDecorationLine: canClarify ? 'underline' : 'none',
                },
              ]}
            >
              {hint}
            </Text>
          </Pressable>
        ) : null}
      </View>
      {showDivider ? (
        <View style={[styles.divider, { backgroundColor: colors.divider }]} />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    minHeight: tokens.touch.min,
    paddingVertical: tokens.spacing.md,
    paddingHorizontal: 0,
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: tokens.spacing.md,
  },
  textCol: {
    flex: 1,
    gap: 4,
  },
  statement: {
    fontSize: tokens.typography.body.fontSize,
    lineHeight: tokens.typography.body.lineHeight,
    letterSpacing: -0.2,
  },
  hintHit: {
    paddingTop: 2,
    paddingVertical: tokens.spacing.xs,
  },
  hint: {
    fontSize: tokens.typography.caption.fontSize,
    lineHeight: tokens.typography.caption.lineHeight,
  },
  prov: {
    fontSize: tokens.typography.caption.fontSize,
    lineHeight: tokens.typography.caption.lineHeight,
    marginTop: 2,
  },
  divider: {
    height: StyleSheet.hairlineWidth,
  },
});
