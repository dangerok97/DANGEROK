import React from 'react';
import { Pressable, StyleSheet, ViewStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { triggerHaptic } from '@/src/theme/haptics';

type Props = {
  icon?: keyof typeof Ionicons.glyphMap;
  onPress?: () => void;
  accessibilityLabel: string;
  style?: ViewStyle;
  testID?: string;
};

export function FAB({ icon = 'add', onPress, accessibilityLabel, style, testID }: Props) {
  const { colors, shadow } = useTheme();
  return (
    <Pressable
      onPress={() => {
        void triggerHaptic('impactMedium');
        onPress?.();
      }}
      style={({ pressed }) => [
        styles.fab,
        {
          backgroundColor: colors.accent,
          transform: [{ scale: pressed ? tokens.motion.pressScale : 1 }],
        },
        shadow('floating') as ViewStyle,
        style,
      ]}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      testID={testID}
    >
      <Ionicons name={icon} size={tokens.icon.size[28]} color={colors.onAccent} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  fab: {
    width: 56,
    height: 56,
    borderRadius: tokens.radius.full,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
