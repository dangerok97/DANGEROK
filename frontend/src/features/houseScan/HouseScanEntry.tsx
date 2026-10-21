import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

export function HouseScanEntry() {
  const router = useRouter();
  const { colors } = useTheme();
  return (
    <Pressable testID="vita-house-scan-entry" accessibilityRole="button"
      accessibilityLabel="Apri pianta e misure della casa" onPress={() => router.push('/casa' as any)}
      style={({ pressed }) => [s.card, { backgroundColor: colors.surface, borderColor: colors.border }, pressed && { opacity: .7 }]}>
      <View style={[s.icon, { backgroundColor: colors.accentMuted }]}>
        <Ionicons name="home-outline" size={24} color={colors.accent} />
      </View>
      <View style={{ flex: 1, gap: 3 }}>
        <Text style={[s.title, { color: colors.textPrimary }]}>Pianta e misure della casa</Text>
        <Text style={[s.subtitle, { color: colors.textSecondary }]}>Ritrova le stanze, consulta le misure e verifica le quote.</Text>
      </View>
      <Ionicons name="arrow-forward" size={20} color={colors.accent} />
    </Pressable>
  );
}

const s = StyleSheet.create({
  card: { flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.md,
    padding: tokens.spacing.lg, borderWidth: 1, borderRadius: tokens.radius.lg, minHeight: 94 },
  icon: { width: 44, height: 44, borderRadius: tokens.radius.md, alignItems: 'center', justifyContent: 'center' },
  title: { fontSize: 18, fontWeight: '700' },
  subtitle: { fontSize: 14, lineHeight: 20 },
});
