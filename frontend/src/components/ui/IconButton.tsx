import React from 'react';
import { Pressable, StyleSheet, ViewStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { triggerHaptic } from '@/src/theme/haptics';

type Props = {
  name: keyof typeof Ionicons.glyphMap;
  onPress?: () => void;
  size?: 16 | 20 | 24 | 28 | 32;
  accessibilityLabel: string;
  disabled?: boolean;
  testID?: string;
  style?: ViewStyle;
};

export function IconButton({
  name,
  onPress,
  size = 24,
  accessibilityLabel,
  disabled,
  testID,
  style,
}: Props) {
  const { colors } = useTheme();
  return (
    <Pressable
      onPress={() => {
        void triggerHaptic('selection');
        onPress?.();
      }}
      disabled={disabled}
      hitSlop={8}
      style={({ pressed }) => [
        styles.btn,
        { opacity: disabled ? 0.4 : pressed ? 0.7 : 1 },
        style,
      ]}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      testID={testID}
    >
      <Ionicons name={name} size={size} color={colors.textPrimary} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  btn: {
    minWidth: tokens.touch.min,
    minHeight: tokens.touch.min,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: tokens.radius.full,
  },
});
