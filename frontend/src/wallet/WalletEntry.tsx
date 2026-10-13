import React from 'react';
import { Pressable, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { VitaHeader } from '@/src/components/vita/VitaChrome';

/** Explicit named re-export keeps the existing Vita header contract unchanged. */
export function WalletVitaHeader(props: React.ComponentProps<typeof VitaHeader>) {
  const { colors } = useTheme();
  const router = useRouter();
  return <View style={{ gap: tokens.spacing.lg }}>
    <VitaHeader {...props} />
    <Pressable onPress={() => router.push('/(tabs)/portafoglio' as any)} accessibilityRole="button" testID="vita-wallet-entry"
      style={({ pressed }) => ({ flexDirection: 'row', alignItems: 'center', gap: 16, borderRadius: tokens.radius.lg,
        borderWidth: 1, borderColor: colors.border, padding: 20, backgroundColor: colors.surface, opacity: pressed ? 0.75 : 1 })}>
      <Ionicons name="wallet-outline" size={28} color={colors.accent} />
      <View style={{ flex: 1 }}><Text style={{ color: colors.textPrimary, fontSize: 17, fontWeight: '600' }}>Portafoglio tessere</Text>
        <Text style={{ color: colors.textSecondary, fontSize: 14, lineHeight: 21 }}>Tessere fedeltà e codici, pronti da mostrare.</Text></View>
      <Ionicons name="chevron-forward" size={20} color={colors.textSecondary} />
    </Pressable>
  </View>;
}
