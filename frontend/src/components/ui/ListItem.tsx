import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

type Props = {
  title: string;
  subtitle?: string;
  left?: React.ReactNode;
  right?: React.ReactNode;
  onPress?: () => void;
  showChevron?: boolean;
  accessibilityLabel?: string;
  testID?: string;
};

export function ListItem({
  title,
  subtitle,
  left,
  right,
  onPress,
  showChevron,
  accessibilityLabel,
  testID,
}: Props) {
  const { colors } = useTheme();
  const content = (
    <>
      {left ? <View style={styles.left}>{left}</View> : null}
      <View style={styles.mid}>
        <Text style={[styles.title, { color: colors.textPrimary }]} numberOfLines={2}>
          {title}
        </Text>
        {subtitle ? (
          <Text style={[styles.sub, { color: colors.textSecondary }]} numberOfLines={2}>
            {subtitle}
          </Text>
        ) : null}
      </View>
      {right}
      {showChevron ? (
        <Ionicons name="chevron-forward" size={tokens.icon.size[20]} color={colors.textTertiary} />
      ) : null}
    </>
  );

  if (onPress) {
    return (
      <Pressable
        onPress={onPress}
        style={({ pressed }) => [
          styles.row,
          { borderBottomColor: colors.divider, opacity: pressed ? 0.75 : 1 },
        ]}
        accessibilityRole="button"
        accessibilityLabel={accessibilityLabel ?? title}
        testID={testID}
      >
        {content}
      </Pressable>
    );
  }

  return (
    <View style={[styles.row, { borderBottomColor: colors.divider }]} testID={testID}>
      {content}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: tokens.touch.min,
    paddingVertical: tokens.spacing.md,
    gap: tokens.spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  left: { alignItems: 'center', justifyContent: 'center' },
  mid: { flex: 1, gap: 2 },
  title: {
    fontSize: tokens.typography.body.fontSize,
    fontWeight: '500',
    letterSpacing: tokens.typography.body.letterSpacing,
  },
  sub: {
    fontSize: tokens.typography.caption.fontSize,
    lineHeight: tokens.typography.caption.lineHeight,
  },
});
