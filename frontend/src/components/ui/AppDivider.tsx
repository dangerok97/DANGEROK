import React from 'react';
import { StyleSheet, View, ViewStyle } from 'react-native';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

type Props = {
  inset?: boolean;
  style?: ViewStyle;
};

export function AppDivider({ inset, style }: Props) {
  const { colors } = useTheme();
  return (
    <View
      style={[
        styles.line,
        { backgroundColor: colors.divider, marginHorizontal: inset ? tokens.spacing.lg : 0 },
        style,
      ]}
      accessibilityElementsHidden
      importantForAccessibility="no"
    />
  );
}

/** Alias */
export const Divider = AppDivider;

const styles = StyleSheet.create({
  line: { height: StyleSheet.hairlineWidth, width: '100%' },
});
