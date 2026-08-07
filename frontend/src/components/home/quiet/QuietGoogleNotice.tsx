import { useState } from 'react';
import { View, Text, StyleSheet, Linking, Platform, Pressable } from 'react-native';
import { useRouter } from 'expo-router';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { api } from '@/src/api/client';
import { triggerHaptic } from '@/src/theme/haptics';

type Props = {
  visible: boolean;
  onDismiss: () => void;
  onConnected?: () => void;
};

/** Subordinate inline notice — not an ad, not an alarm. */
export function QuietGoogleNotice({ visible, onDismiss, onConnected }: Props) {
  const { colors } = useTheme();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  if (!visible) return null;

  const connect = async () => {
    void triggerHaptic('selection');
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
    <View
      style={[styles.wrap, { borderColor: colors.divider }]}
      testID="google-banner"
      accessibilityRole="summary"
    >
      <Text style={[styles.text, { color: colors.textSecondary }]}>
        Google Calendar non collegato — arricchisce le priorità.
      </Text>
      <View style={styles.actions}>
        <Pressable
          onPress={connect}
          disabled={busy}
          testID="btn-google-collega"
          accessibilityRole="button"
          accessibilityLabel="Collega Google Calendar"
          style={styles.hit}
        >
          <Text style={[styles.link, { color: colors.accent }]}>
            {busy ? '…' : 'Collega'}
          </Text>
        </Pressable>
        <Pressable
          onPress={onDismiss}
          testID="btn-google-non-ora"
          accessibilityRole="button"
          style={styles.hit}
        >
          <Text style={[styles.linkMuted, { color: colors.textTertiary }]}>Non ora</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: 6,
    paddingVertical: tokens.spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  text: {
    fontSize: tokens.typography.caption.fontSize,
    lineHeight: 18,
  },
  actions: { flexDirection: 'row', gap: tokens.spacing.lg },
  hit: { minHeight: tokens.touch.min, justifyContent: 'center' },
  link: { fontSize: 13, fontWeight: '600' },
  linkMuted: { fontSize: 13, fontWeight: '500' },
});
