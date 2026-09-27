import { Platform, Pressable, ScrollView, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { PlacesSection } from '@/src/components/vita/PlacesSection';
import { DesktopShell } from '@/src/shell';
import { useTheme } from '@/src/theme/ThemeProvider';

export default function PlacesScreen() {
  const router = useRouter();
  const { colors } = useTheme();
  return <DesktopShell active="contesti">
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.backgroundPrimary }}>
      <ScrollView contentContainerStyle={{ padding: 24, gap: 24, width: '100%', maxWidth: 880, alignSelf: 'center' }}>
        <Pressable accessibilityRole="button" accessibilityLabel="Torna a Vita" onPress={() => router.replace('/vita' as any)} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, minHeight: 44 }}>
          <Ionicons name="chevron-back" size={18} color={colors.textSecondary} />
          <Text style={{ color: colors.textSecondary }}>Vita</Text>
        </Pressable>
        <View style={{ gap: 10 }}>
          <Text accessibilityRole="header" style={{ color: colors.textPrimary, fontSize: 32, fontWeight: '600' }}>I tuoi luoghi</Text>
          <Text style={{ color: colors.textSecondary, fontSize: 15, lineHeight: 22 }}>Dai un nome ai posti che contano. Apri un luogo per vedere le presenze registrate e preparare il percorso.</Text>
          {Platform.OS === 'web' ? <Text style={{ color: colors.textTertiary, fontSize: 13, lineHeight: 19 }}>Sul browser la posizione si aggiorna mentre usi ORA. Il riconoscimento a schermo spento richiede l’app nativa e il permesso in background.</Text> : null}
        </View>
        <PlacesSection onOpenOra={() => router.push('/ora' as any)} />
      </ScrollView>
    </SafeAreaView>
  </DesktopShell>;
}
