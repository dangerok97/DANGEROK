import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

/**
 * VITA's primary wallet entry. A first-class, visible row alongside Places and
 * life areas, NOT a hidden addition to VitaHeader via a barrel re-export.
 * It does not require life-map, bank data or a stored card to be displayed.
 */
export function WalletEntry() {
  const { colors } = useTheme();
  const router = useRouter();

  return (
    <Pressable
      onPress={() => router.push('/portafoglio' as any)}
      accessibilityRole="button"
      accessibilityLabel="Apri il portafoglio tessere fedeltà"
      testID="vita-wallet-entry"
      style={({ pressed }) => [
        styles.card,
        { backgroundColor: colors.surface, borderColor: colors.border },
        pressed && { opacity: 0.72 },
      ]}
    >
      <View style={[styles.iconBox, { backgroundColor: colors.accentMuted }]}>
        <Ionicons name="card-outline" color={colors.accent} size={24} />
      </View>
      <View style={styles.copy}>
        <Text style={[styles.title, { color: colors.textPrimary }]}>Portafoglio tessere</Text>
        <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
          Carte fedeltà, codici a barre e QR. Apri una tessera alla cassa.
        </Text>
      </View>
      <Ionicons name="arrow-forward" size={22} color={colors.accent} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: tokens.spacing.md,
    borderWidth: 1,
    borderRadius: tokens.radius.lg,
    padding: tokens.spacing.lg,
    minHeight: 94,
  },
  iconBox: {
    width: 44,
    height: 44,
    borderRadius: tokens.radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  copy: { flex: 1, minWidth: 0, gap: 3 },
  title: { fontSize: 18, fontWeight: '700' },
  subtitle: { fontSize: 14, lineHeight: 20 },
});