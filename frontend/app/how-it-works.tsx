import { View, Text, StyleSheet, Pressable, ScrollView } from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { Stack, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import Animated, { FadeInDown } from 'react-native-reanimated';

import { tokens } from '@/src/theme/tokens';
import { haptic } from '@/src/utils/haptic';
import { ActionBtn } from '@/src/components/ui/ActionBtn';

const STEPS = [
  {
    icon: 'calendar-outline',
    title: 'Collega il tuo calendario',
    body: 'ORA legge (in sola lettura) i tuoi impegni per capire quando sei libero e quando hai eventi importanti.',
  },
  {
    icon: 'sparkles-outline',
    title: 'Capiamo la tua giornata',
    body: 'Ogni giorno ORA calcola un riassunto: quanti impegni hai, dove sono le finestre libere, cosa merita attenzione.',
  },
  {
    icon: 'flag-outline',
    title: 'Ti diciamo cosa fare adesso',
    body: 'Una sola Decision alla volta: quella più importante per te in questo momento, con la spiegazione del perché.',
  },
  {
    icon: 'shield-checkmark-outline',
    title: 'I tuoi dati restano tuoi',
    body: 'ORA non pubblica nulla, non invita nessuno, non scrive sul tuo calendario. Puoi disconnetterlo in qualsiasi momento.',
  },
];

export default function HowItWorks() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  return (
    <SafeAreaView style={styles.safe} edges={['top']} testID="how-it-works">
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Pressable
          onPress={() => { haptic('tap'); router.back(); }}
          style={({ pressed }) => [styles.backBtn, pressed && styles.pressed]}
          accessibilityRole="button" accessibilityLabel="Torna indietro" hitSlop={12}
        >
          <Ionicons name="chevron-back" size={22} color={tokens.color.onSurface} />
        </Pressable>
        <Text style={styles.title}>Come funziona</Text>
        <View style={{ width: 32 }} />
      </View>
      <ScrollView
        contentContainerStyle={{ padding: 20, paddingBottom: insets.bottom + 24, gap: 16 }}
        showsVerticalScrollIndicator={false}
      >
        <Text style={styles.hero}>
          ORA ti aiuta a decidere <Text style={styles.heroAccent}>cosa fare adesso</Text>, senza rumore.
        </Text>
        <Text style={styles.subhero}>
          Bastano un paio di minuti per collegare il tuo Google Calendar e iniziare.
        </Text>

        {STEPS.map((s, i) => (
          <Animated.View key={s.title} entering={FadeInDown.duration(240).delay(i * 60)} style={styles.step}>
            <View style={styles.stepIcon}>
              <Ionicons name={s.icon as any} size={20} color={tokens.color.brand} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.stepTitle}>{s.title}</Text>
              <Text style={styles.stepBody}>{s.body}</Text>
            </View>
          </Animated.View>
        ))}

        <View style={{ marginTop: 12 }}>
          <ActionBtn
            primary
            icon="arrow-back"
            label="Torna alla Home"
            onPress={() => { haptic('tap'); router.back(); }}
            testID="btn-back-home"
          />
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: tokens.color.surface },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 12, paddingVertical: 12,
  },
  backBtn: { width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center' },
  title: { fontSize: 17, fontWeight: '700', color: tokens.color.onSurface },
  hero: { fontSize: 24, fontWeight: '700', color: tokens.color.onSurface, lineHeight: 30, letterSpacing: -0.3 },
  heroAccent: { color: tokens.color.brand },
  subhero: { fontSize: 14, color: tokens.color.onSurfaceMuted, lineHeight: 20 },
  step: {
    flexDirection: 'row', gap: 12, alignItems: 'flex-start',
    backgroundColor: tokens.color.surfaceSecondary,
    padding: tokens.spacing.lg, borderRadius: tokens.radius.lg,
    borderWidth: 1, borderColor: tokens.color.border,
  },
  stepIcon: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: tokens.color.surfaceTertiary,
    alignItems: 'center', justifyContent: 'center',
  },
  stepTitle: { fontSize: 15, fontWeight: '600', color: tokens.color.onSurface },
  stepBody: { fontSize: 13, color: tokens.color.onSurfaceMuted, lineHeight: 19, marginTop: 4 },
  pressed: { opacity: 0.7 },
});
