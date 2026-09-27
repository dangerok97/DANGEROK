import type React from 'react';
import { Pressable, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

const STARTERS = [
  { icon: 'sunny-outline', title: 'Fai spazio alla giornata', detail: 'Impegni, priorità e un prossimo passo.', text: 'Guarda i miei impegni e le informazioni disponibili: cosa merita la mia attenzione oggi?' },
  { icon: 'navigate-outline', title: 'Prepariamo il percorso', detail: 'Partenza, meteo e tempi disponibili.', text: 'Aiutami a preparare il prossimo spostamento usando i miei luoghi e impegni. Verifica meteo e traffico se sono disponibili; chiedimi solo i dati indispensabili che mancano.' },
  { icon: 'wallet-outline', title: 'Controlliamo le spese', detail: 'Partiamo dai contratti e dai documenti.', text: 'Controlla i documenti disponibili e le ricerche aggiornate: ci sono opportunità concrete per ridurre le mie spese? Distingui le stime dai risparmi verificati.' },
  { icon: 'layers-outline', title: 'Mettiamo ordine', detail: 'Trasforma un pensiero in qualcosa di concreto.', text: 'Aiutami a mettere ordine nelle cose rimaste aperte. Usa il contesto disponibile e proponi un prossimo passo concreto.' },
] as const;

export function OraWelcome({ children, onPrompt }: { children: React.ReactNode; onPrompt: (text: string) => void }) {
  const { colors } = useTheme();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const compact = width < 650;
  return (
    <View style={[styles.inner, { paddingHorizontal: compact ? 8 : 24 }]} testID="ora-welcome">
          <View style={styles.topline}>
            <Text style={[styles.eyebrow, { color: colors.textTertiary }]}>IL TUO SPAZIO CON ORA</Text>
            <Pressable accessibilityRole="button" accessibilityLabel="Apri la tua Vita e i tuoi luoghi" onPress={() => router.push('/vita' as any)} style={styles.lifeLink}>
              <Text style={{ color: colors.textSecondary, fontSize: 13 }}>La tua Vita</Text>
              <Ionicons name="arrow-forward" size={16} color={colors.textSecondary} />
            </Pressable>
          </View>
          <View style={styles.hero}>
            <View style={[styles.orbit, { borderColor: colors.border, backgroundColor: colors.surface }]} accessibilityElementsHidden>
              <LinearGradient colors={[colors.accent, colors.textPrimary]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.core}>
                <Ionicons name="sparkles" size={29} color={colors.onAccent} />
              </LinearGradient>
            </View>
            <Text accessibilityRole="header" style={[styles.title, { color: colors.textPrimary, fontSize: compact ? 34 : 46, lineHeight: compact ? 41 : 54 }]}>
              Una cosa in meno{ '\n' }a cui pensare.
            </Text>
            <Text style={[styles.body, { color: colors.textSecondary }]}>
              Raccontami un pensiero, un impegno o qualcosa da risolvere. Partiamo da ciò che conta per te.
            </Text>
          </View>
          <View style={[styles.composer, { backgroundColor: colors.surface, borderColor: colors.border }]}>
            {children}
            <Text style={[styles.caption, { color: colors.textTertiary }]}>Puoi scegliere uno spunto qui sotto e modificarlo prima di inviarlo.</Text>
          </View>
          <Text style={[styles.eyebrow, { color: colors.textTertiary, marginTop: 12 }]}>DA DOVE COMINCIAMO?</Text>
          <View style={[styles.callCard, { backgroundColor: colors.surface, borderColor: colors.border }]} testID="ora-calls">
            <View style={styles.callHeading}>
              <View style={[styles.callIcon, { backgroundColor: colors.backgroundSecondary }]}>
                <Ionicons name="call-outline" size={24} color={colors.accent} />
              </View>
              <View style={styles.callCopy}>
                <Text accessibilityRole="header" style={[styles.callTitle, { color: colors.textPrimary }]}>Una chiamata per te</Text>
                <Text style={[styles.cardDetail, { color: colors.textSecondary }]}>Scegli chi contattare e cosa chiedere. Prepariamo la telefonata, poi dai tu il via.</Text>
              </View>
            </View>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Prepara una chiamata con ORA"
                onPress={() => router.push('/prepara-chiamata' as any)}
                testID="ora-prepare-call"
                style={({ pressed }) => [styles.callButton, { alignSelf: compact ? 'stretch' : 'flex-start', backgroundColor: colors.accent, opacity: pressed ? 0.8 : 1 }]}
              >
                <Text style={[styles.callButtonText, { color: colors.onAccent }]}>Prepara una chiamata</Text>
                <Ionicons name="arrow-forward" size={18} color={colors.onAccent} />
              </Pressable>
          </View>
          <View style={styles.grid}>
            {STARTERS.map(item => (
              <Pressable key={item.title} accessibilityRole="button" accessibilityLabel={`Prepara una richiesta: ${item.title}`} onPress={() => onPrompt(item.text)} style={({ pressed }) => [styles.card, { width: compact ? '100%' : '48.5%', backgroundColor: pressed ? colors.backgroundSecondary : colors.surface, borderColor: colors.border }]}>
                <View style={styles.cardTop}>
                  <Ionicons name={item.icon} size={22} color={colors.accent} />
                  <Ionicons name="arrow-up-outline" size={15} color={colors.textTertiary} />
                </View>
                <Text style={[styles.cardTitle, { color: colors.textPrimary }]}>{item.title}</Text>
                <Text style={[styles.cardDetail, { color: colors.textSecondary }]}>{item.detail}</Text>
              </Pressable>
            ))}
          </View>
          <View style={styles.footer}>
            <Ionicons name="git-branch-outline" size={16} color={colors.textTertiary} />
            <Text style={[styles.footerText, { color: colors.textTertiary }]}>Le informazioni che condividi aiutano ORA a collegare impegni, luoghi e documenti.</Text>
          </View>
    </View>
  );
}
const styles = StyleSheet.create({
  root: { flex: 1 }, inner: { flexGrow: 1, paddingTop: 28, gap: 20, maxWidth: 880, width: '100%', alignSelf: 'center' },
  topline: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' },
  lifeLink: { flexDirection: 'row', alignItems: 'center', gap: 8, minHeight: 44 },
  eyebrow: { fontSize: 11, fontWeight: '600', letterSpacing: 1.4 },
  hero: { alignItems: 'center', paddingTop: 16, paddingBottom: 12, gap: 18 },
  orbit: { width: 88, height: 88, borderRadius: 44, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
  core: { width: 64, height: 64, borderRadius: 32, alignItems: 'center', justifyContent: 'center' },
  title: { fontWeight: '600', letterSpacing: -1.2, textAlign: 'center' },
  body: { fontSize: 16, lineHeight: 24, textAlign: 'center', maxWidth: 480 },
  composer: { padding: 14, borderRadius: 24, borderWidth: StyleSheet.hairlineWidth, gap: 12 },
  caption: { fontSize: 12, lineHeight: 18, textAlign: 'center' },
  callCard: { borderRadius: 20, borderWidth: StyleSheet.hairlineWidth, padding: 20, gap: 18 },
  callHeading: { flexDirection: 'row', alignItems: 'flex-start', gap: 14 },
  callIcon: { width: 48, height: 48, borderRadius: 16, alignItems: 'center', justifyContent: 'center' },
  callCopy: { flex: 1, gap: 6 },
  callTitle: { fontSize: 20, lineHeight: 26, fontWeight: '600' },
  callButton: { minHeight: 48, paddingHorizontal: 16, paddingVertical: 12, borderRadius: 14, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10 },
  callButtonText: { fontSize: 14, lineHeight: 20, fontWeight: '600', flexShrink: 1 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', gap: 14 },
  card: { borderRadius: 20, borderWidth: StyleSheet.hairlineWidth, padding: 20, gap: 8, minHeight: 150 },
  cardTop: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 },
  cardTitle: { fontSize: 16, fontWeight: '600' }, cardDetail: { fontSize: 13, lineHeight: 19 },
  footer: { flexDirection: 'row', gap: 10, alignItems: 'center', paddingHorizontal: tokens.spacing.md, paddingTop: 4 },
  footerText: { flex: 1, fontSize: 12, lineHeight: 18 },
});
