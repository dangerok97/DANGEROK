import { Pressable, StyleSheet, Text, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { tokens } from '@/src/theme/tokens';

type Props = {
  label: string;
  icon?: keyof typeof Ionicons.glyphMap;
  onPress?: () => void;
  primary?: boolean;
  loading?: boolean;
  disabled?: boolean;
  testID?: string;
  accessibilityHint?: string;
  variant?: 'default' | 'ghost' | 'danger';
};

export function ActionBtn({
  label, icon, onPress, primary, loading, disabled, testID, accessibilityHint, variant = 'default',
}: Props) {
  const dim = loading || disabled;
  return (
    <Pressable
      onPress={onPress}
      disabled={dim}
      style={({ pressed }) => [
        styles.btn,
        variant === 'ghost' && styles.ghost,
        variant === 'danger' && styles.danger,
        primary && styles.primary,
        dim && styles.dim,
        pressed && styles.pressed,
      ]}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ busy: !!loading, disabled: dim }}
      testID={testID}
      hitSlop={8}
    >
      {loading ? (
        <ActivityIndicator size="small" color={primary ? tokens.color.onBrand : tokens.color.onSurface} />
      ) : (
        <>
          {icon && (
            <Ionicons
              name={icon}
              size={16}
              color={primary ? tokens.color.onBrand : variant === 'danger' ? tokens.color.error : tokens.color.onSurface}
            />
          )}
          <Text
            style={[
              styles.text,
              primary && styles.textPrimary,
              variant === 'danger' && styles.textDanger,
            ]}
          >
            {label}
          </Text>
        </>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  btn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    minHeight: tokens.touch.min, minWidth: tokens.touch.min,
    paddingHorizontal: 14, paddingVertical: 10,
    borderRadius: tokens.radius.md,
    backgroundColor: tokens.color.surfaceTertiary,
    borderWidth: 1, borderColor: tokens.color.border,
  },
  ghost: { backgroundColor: 'transparent', borderColor: tokens.color.borderStrong },
  danger: { backgroundColor: tokens.color.errorBg, borderColor: tokens.color.error },
  primary: { backgroundColor: tokens.color.brand, borderColor: tokens.color.brand },
  dim: { opacity: 0.6 },
  pressed: { opacity: 0.7, transform: [{ scale: 0.98 }] },
  text: { fontSize: 13, color: tokens.color.onSurface, fontWeight: '600' },
  textPrimary: { color: tokens.color.onBrand },
  textDanger: { color: tokens.color.error },
});
