import { View, Text, StyleSheet, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

export function OfflineBanner() {
  const { colors } = useTheme();
  return (
    <View
      style={[styles.banner, { backgroundColor: colors.warningBg, borderColor: colors.warning }]}
      accessibilityRole="alert"
      accessibilityLiveRegion="polite"
      testID="offline-banner"
    >
      <Ionicons name="cloud-offline-outline" size={16} color={colors.warning} />
      <Text style={[styles.text, { color: colors.textPrimary }]}>
        Sei offline. I dati mostrati potrebbero non essere aggiornati.
      </Text>
    </View>
  );
}

export function ErrorBanner({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  const { colors } = useTheme();
  return (
    <View
      style={[styles.banner, { backgroundColor: colors.errorBg, borderColor: colors.error }]}
      accessibilityRole="alert"
      accessibilityLiveRegion="polite"
      testID="error-banner"
    >
      <Ionicons name="alert-circle" size={16} color={colors.error} />
      <Text style={[styles.text, { color: colors.textPrimary, flex: 1 }]}>{message}</Text>
      <Pressable
        hitSlop={12}
        onPress={onDismiss}
        accessibilityLabel="Chiudi errore"
        accessibilityRole="button"
        style={styles.close}
      >
        <Ionicons name="close" size={16} color={colors.textSecondary} />
      </Pressable>
    </View>
  );
}

export function PartialWarning() {
  const { colors } = useTheme();
  return (
    <View
      style={[styles.banner, { backgroundColor: colors.warningBg, borderColor: colors.warning }]}
      testID="partial-warning"
    >
      <Text style={[styles.text, { color: colors.textPrimary }]}>
        Alcune fonti non sono disponibili. Mostro i dati parziali.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.md,
    padding: 12,
  },
  text: { fontSize: tokens.typography.caption.fontSize, lineHeight: 18, flexShrink: 1 },
  close: { minWidth: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center' },
});
