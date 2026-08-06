import { View, Text, StyleSheet, Pressable } from 'react-native';
import Animated, { FadeIn, FadeOut } from 'react-native-reanimated';
import { Ionicons } from '@expo/vector-icons';
import { tokens } from '@/src/theme/tokens';
import { formatRelativeAgo } from '@/src/utils/labels';

/** Sync meta under PARLA CON ORA — no competing "Adesso" hero title. */
export function HomeHeader({ online, lastSuccessAt }: { online: boolean; lastSuccessAt: Date | null }) {
  return (
    <View style={styles.header} testID="home-sync-meta">
      <SyncMeta online={online} lastSuccessAt={lastSuccessAt} />
    </View>
  );
}

function SyncMeta({ online, lastSuccessAt }: { online: boolean; lastSuccessAt: Date | null }) {
  if (!online) {
    return (
      <View style={styles.metaRow}>
        <View style={[styles.dot, { backgroundColor: tokens.color.warning }]} />
        <Text style={styles.metaText}>Offline</Text>
      </View>
    );
  }
  if (!lastSuccessAt) return null;
  return (
    <View
      style={styles.metaRow}
      accessibilityLabel={`Ultimo aggiornamento ${formatRelativeAgo(lastSuccessAt)}`}
    >
      <View style={[styles.dot, { backgroundColor: tokens.color.success }]} />
      <Text style={styles.metaText}>Aggiornato {formatRelativeAgo(lastSuccessAt)}</Text>
    </View>
  );
}

export function OfflineBanner() {
  return (
    <Animated.View
      entering={FadeIn.duration(tokens.motion.fast)}
      style={[styles.banner, styles.offline]}
      accessibilityRole="alert"
      accessibilityLiveRegion="polite"
      testID="offline-banner"
    >
      <Ionicons name="cloud-offline-outline" size={16} color={tokens.color.warning} />
      <Text style={styles.bannerText}>Sei offline. I dati mostrati potrebbero non essere aggiornati.</Text>
    </Animated.View>
  );
}

export function ErrorBanner({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  return (
    <Animated.View
      entering={FadeIn.duration(tokens.motion.fast)}
      exiting={FadeOut.duration(tokens.motion.fast)}
      style={[styles.banner, styles.error]}
      accessibilityRole="alert"
      accessibilityLiveRegion="polite"
      testID="error-banner"
    >
      <Ionicons name="alert-circle" size={16} color={tokens.color.error} />
      <Text style={styles.bannerText}>{message}</Text>
      <Pressable hitSlop={12} onPress={onDismiss} accessibilityLabel="Chiudi errore" accessibilityRole="button">
        <Ionicons name="close" size={16} color={tokens.color.onSurfaceMuted} />
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  header: {
    marginBottom: tokens.spacing.sm,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
  },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingBottom: 2 },
  dot: { width: 6, height: 6, borderRadius: 3 },
  metaText: { fontSize: 11, color: tokens.color.onSurfaceDim, fontWeight: '500' },
  banner: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    borderRadius: tokens.radius.md, padding: 12, borderWidth: 1,
  },
  offline: { backgroundColor: tokens.color.warningBg, borderColor: tokens.color.warning },
  error: { backgroundColor: tokens.color.errorBg, borderColor: tokens.color.error },
  bannerText: { flex: 1, color: tokens.color.onSurface, fontSize: 13 },
});
