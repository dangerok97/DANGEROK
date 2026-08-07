import React from 'react';
import { StyleSheet, TextInput, TextInputProps, View, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

type Props = TextInputProps & {
  onClear?: () => void;
};

export function SearchInput({ onClear, value, style, ...rest }: Props) {
  const { colors } = useTheme();
  const showClear = Boolean(value && String(value).length > 0);
  return (
    <View
      style={[
        styles.wrap,
        { backgroundColor: colors.backgroundSecondary, borderColor: colors.border },
        style as object,
      ]}
    >
      <Ionicons name="search" size={tokens.icon.size[20]} color={colors.textTertiary} />
      <TextInput
        value={value}
        placeholderTextColor={colors.placeholder}
        style={[styles.input, { color: colors.textPrimary }]}
        accessibilityRole="search"
        accessibilityLabel={rest.accessibilityLabel ?? 'Cerca'}
        returnKeyType="search"
        {...rest}
      />
      {showClear && onClear ? (
        <Pressable
          onPress={onClear}
          hitSlop={8}
          accessibilityRole="button"
          accessibilityLabel="Cancella ricerca"
          style={styles.clear}
        >
          <Ionicons name="close-circle" size={tokens.icon.size[20]} color={colors.textTertiary} />
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: tokens.spacing.sm,
    minHeight: tokens.touch.min,
    borderRadius: tokens.radius.full,
    borderWidth: 1,
    paddingHorizontal: tokens.spacing.lg,
  },
  input: {
    flex: 1,
    fontSize: tokens.typography.body.fontSize,
    paddingVertical: tokens.spacing.sm,
  },
  clear: {
    minWidth: 32,
    minHeight: 32,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
