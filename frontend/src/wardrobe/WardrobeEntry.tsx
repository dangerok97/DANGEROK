import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

/** One secondary VITA entry; no additional tab or on-load prompts. */
export function WardrobeEntry() {
  const router = useRouter();
  const { colors } = useTheme();
  return (
    <Pressable accessibilityRole="button" accessibilityLabel="Apri il guardaroba virtuale"
      testID="vita-wardrobe-entry" onPress={() => router.push('/guardaroba' as any)}
      style={({ pressed }) => [s.card, { backgroundColor: colors.surface, borderColor: colors.border },
        pressed && { opacity: .7 }]}>
      <View style={[s.icon, { backgroundColor: colors.accentMuted }]}>
        <Ionicons name="shirt-outline" size={24} color={colors.accent} />
      </View>
      <View style={{ flex: 1, gap: 3 }}>
        <Text style={[s.title, { color: colors.textPrimary }]}>Il mio guardaroba</Text>
        <Text style={[s.subtitle, { color: colors.textSecondary }]}>
          Salva i tuoi capi e crea i primi abbinamenti per occasione.
        </Text>
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
