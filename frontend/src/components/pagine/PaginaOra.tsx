/**
 * L'impalcatura delle pagine che si aprono dalla Home.
 *
 *     OGNI LINK HA LA SUA PAGINA, E OGNI PAGINA HA LA STESSA ARIA.
 *
 * V3.21.3b: «Vedi agenda», «Vedi tutto», «4 da rispondere», «1 aggiornamento»
 * portavano tutti alla stessa «Situazione completa». Adesso sono quattro
 * superfici diverse — e perché non sembrino quattro prodotti diversi, la
 * cornice è una sola: barra laterale a sinistra sul desktop, un titolo, una
 * riga che dice a che cosa serve la pagina, e il ritorno da dove si è entrati.
 */
import type { ReactNode } from 'react';
import { Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import { DesktopShell, type RailKey } from '@/src/shell';
import { ora, oraType } from '@/src/theme/oraSurface';

export function PaginaOra({
  titolo,
  sottotitolo,
  attiva,
  azione,
  children,
  testID,
}: {
  titolo: string;
  sottotitolo?: string;
  /** Quale voce della barra resta accesa mentre si è qui. */
  attiva?: RailKey;
  /** Una cosa sola in alto a destra, quando serve davvero. */
  azione?: ReactNode;
  children: ReactNode;
  testID?: string;
}) {
  const router = useRouter();

  return (
    <DesktopShell active={attiva}>
      <ScrollView
        style={{ backgroundColor: ora.canvas }}
        contentContainerStyle={styles.corpo}
        showsVerticalScrollIndicator={false}
        testID={testID}
      >
        <View style={styles.testa}>
          <Pressable
            onPress={() => (router.canGoBack() ? router.back() : router.replace('/'))}
            accessibilityRole="button"
            accessibilityLabel="Torna indietro"
            style={({ pressed }) => [styles.indietro, pressed && { opacity: 0.6 }]}
            testID="pagina-indietro"
          >
            <Ionicons name="chevron-back" size={18} color={ora.ink2} />
            <Text style={[oraType.small, { color: ora.ink2 }]}>Indietro</Text>
          </Pressable>
          {azione ? <View style={styles.azione}>{azione}</View> : null}
        </View>

        <Text
          style={[oraType.hero, { color: ora.ink }]}
          accessibilityRole="header"
          aria-level={1}
        >
          {titolo}
        </Text>
        {sottotitolo ? (
          <Text style={[oraType.body, { color: ora.ink3, marginTop: 6 }]}>{sottotitolo}</Text>
        ) : null}

        <View style={styles.contenuto}>{children}</View>
      </ScrollView>
    </DesktopShell>
  );
}

/**
 * Quando non c'è niente da mostrare, si dice perché — e non si finge.
 *
 * Una pagina vuota con un'illustrazione allegra fa pensare a un errore; una
 * frase che dice che cosa manca dice anche che cosa fare.
 */
export function NienteQui({ testo, testID }: { testo: string; testID?: string }) {
  return (
    <View style={styles.vuoto} testID={testID}>
      <Ionicons name="ellipse-outline" size={18} color={ora.ink3} />
      <Text style={[oraType.body, { color: ora.ink3, flex: 1 }]}>{testo}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  corpo: {
    paddingHorizontal: Platform.OS === 'web' ? 40 : 20,
    paddingTop: 28,
    paddingBottom: 64,
    maxWidth: 1100,
    width: '100%',
    alignSelf: 'center',
  },
  testa: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 18,
  },
  indietro: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingVertical: 6 },
  azione: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  contenuto: { marginTop: 24, gap: 16 },
  vuoto: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 22,
    paddingHorizontal: 20,
    borderRadius: ora.radius.card,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: ora.hairline,
    backgroundColor: ora.surface,
  },
});
