import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

/** Cucina belongs to VITA, not the main tab bar. */
export function RecipeEntry() {
  const router = useRouter();
  const { colors } = useTheme();
  return (
    <Pressable testID="vita-recipe-entry" accessibilityRole="button"
      accessibilityLabel="Apri il ricettario Cucina"
      onPress={() => router.push('/cucina' as any)}
      style={({ pressed }) => [styles.card,
        { backgroundColor: colors.surface, borderColor: colors.border }, pressed && { opacity: 0.72 }]}>
      <View style={[styles.icon, { backgroundColor: colors.accentMuted }]}>
        <Ionicons name="restaurant-outline" size={24} color={colors.accent} />
      </View>
      <View style={{ flex: 1, gap: 3 }}>
        <Text style={[styles.title, { color: colors.textPrimary }]}>Cucina e ricette</Text>
        <Text style={[styles.description, { color: colors.textSecondary }]}>
          Salva ricette da Instagram, TikTok, siti o foto. Cucina passo passo, porzioni e spesa.
        </Text>
      </View>
      <Ionicons name="arrow-forward" size={20} color={colors.accent} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.md,
    borderRadius: tokens.radius.lg, padding: tokens.spacing.lg, borderWidth: 1, minHeight: 94 },
  icon: { height: 44, width: 44, alignItems: 'center', justifyContent: 'center',
    borderRadius: tokens.radius.md },
  title: { fontSize: 18, fontWeight: '700' },
  description: { fontSize: 14, lineHeight: 20 },
});
