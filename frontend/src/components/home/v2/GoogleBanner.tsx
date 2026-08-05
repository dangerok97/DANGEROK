import { useState } from 'react';
import { View, Text, StyleSheet, Linking, Platform } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { tokens } from '@/src/theme/tokens';
import { ActionBtn } from '@/src/components/ui/ActionBtn';
import { api } from '@/src/api/client';
import { haptic } from '@/src/utils/haptic';

type Props = {
  visible: boolean;
  onDismiss: () => void;
  onConnected?: () => void;
};

/** Compact banner only — large connect card removed from Home. */
export function GoogleBanner({ visible, onDismiss, onConnected }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  if (!visible) return null;

  const connect = async () => {
    haptic('tap');
    setBusy(true);
    try {
      const r = await api.googleCalendarOAuthStart();
      if (r.authorize_url) {
        if (Platform.OS === 'web' && typeof window !== 'undefined') {
          window.location.assign(r.authorize_url);
        } else {
          await Linking.openURL(r.authorize_url);
        }
        onConnected?.();
      }
    } catch {
      router.push('/settings');
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.banner} testID="google-banner">
      <Ionicons name="calendar-outline" size={18} color={tokens.color.onSurface} />
      <View style={styles.body}>
        <Text style={styles.title}>Google Calendar non collegato</Text>
        <Text style={styles.sub}>Collega per arricchire le priorità. Config completa in Impostazioni.</Text>
      </View>
      <View style={styles.actions}>
        <ActionBtn primary label="Collega" icon="logo-google" onPress={connect} loading={busy} testID="btn-google-collega" />
        <ActionBtn variant="ghost" label="Non ora" onPress={onDismiss} testID="btn-google-non-ora" />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: tokens.radius.md,
    padding: tokens.spacing.md,
    gap: 10,
    borderWidth: 1,
    borderColor: tokens.color.border,
  },
  body: { gap: 2 },
  title: { fontSize: 14, fontWeight: '600', color: tokens.color.onSurface },
  sub: { fontSize: 12, color: tokens.color.onSurfaceMuted, lineHeight: 17 },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
});
