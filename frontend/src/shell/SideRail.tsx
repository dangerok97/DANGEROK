/**
 * La barra laterale di ORA — una sola, per ogni schermata desktop.
 *
 * V3.21.3: prima la disegnava soltanto la barra delle tab, e le schermate che
 * vivono fuori da `(tabs)` — la conversazione, Conosciamoci, la preparazione
 * di una telefonata — si aprivano senza navigazione, come pagine di un altro
 * prodotto. Adesso la barra è un componente: la usa la barra delle tab e la
 * usa `DesktopShell`, e le due non possono più divergere.
 *
 * Composizione dalla reference approvata: marchio e motto in alto, le sei
 * destinazioni con la pillola azzurra per quella corrente, una card quieta
 * che dice che cos'è ORA, e in fondo la persona.
 */
import { Image, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';

import { useAuth } from '@/src/contexts/AuthContext';
import { useTheme } from '@/src/theme/ThemeProvider';
import { ora } from '@/src/theme/oraSurface';
import { AMBIENT_RAIL_WIDTH } from './constants';
import { AMBIENT_ACCOUNT_ITEM, AMBIENT_NAV_ITEMS, type AmbientNavKey } from './navItems';
import { OraBrand } from './OraBrand';
import { Avatar, titleCase } from './RailAccount';

export type RailKey = AmbientNavKey | 'profilo' | null;

export function SideRail({
  active,
  onNavigate,
  topInset = 0,
  bottomInset = 0,
}: {
  active: RailKey;
  onNavigate: (key: AmbientNavKey | 'profilo') => void;
  topInset?: number;
  bottomInset?: number;
}) {
  const { colors } = useTheme();
  const { user } = useAuth();
  const nome = titleCase((user?.name || '').trim() || (user?.email || '').split('@')[0]) || 'Account';

  const go = (key: AmbientNavKey | 'profilo') => {
    if (Platform.OS !== 'web') void Haptics.selectionAsync();
    onNavigate(key);
  };

  return (
    <View
      style={[
        styles.rail,
        {
          paddingTop: Math.max(topInset, 22),
          paddingBottom: Math.max(bottomInset, 18),
          backgroundColor: ora.canvas,
          borderRightColor: ora.hairline,
        },
      ]}
      testID="ambient-rail"
      accessibilityLabel="Navigazione Ambient"
    >
      <View style={styles.brand}>
        <OraBrand size={36} />
        <Text style={[styles.motto, { color: ora.ink3 }]}>Più tempo per ciò che conta</Text>
      </View>

      <View style={styles.items}>
        {AMBIENT_NAV_ITEMS.map((item) => {
          const selected = active === item.key;
          return (
            <Pressable
              key={item.key}
              onPress={() => go(item.route as AmbientNavKey)}
              accessibilityRole="tab"
              accessibilityState={{ selected }}
              accessibilityLabel={item.accessibilityLabel}
              testID={`ambient-tab-${item.key}`}
              style={({ pressed, hovered }: any) => [
                styles.item,
                selected && { backgroundColor: ora.activeBg },
                !selected && hovered && { backgroundColor: ora.hover },
                pressed && { opacity: 0.75 },
              ]}
            >
              <Ionicons
                name={selected ? item.iconActive : item.icon}
                size={22}
                color={selected ? ora.cta : ora.ink2}
              />
              <Text
                style={[
                  styles.label,
                  { color: selected ? ora.ink : ora.ink2, fontWeight: selected ? '600' : '400' },
                ]}
                numberOfLines={1}
              >
                {item.label}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {/*
        Non è un bottone e non promette niente: dice che cos'è ORA, con la
        stessa frase della reference.

            SOTTO CI VA UN'IMMAGINE, NON DUE RETTANGOLI ARROTONDATI.

        Qui c'erano due `View` con un raggio grande a fare da colline: da
        vicino si vedevano per quello che erano — forme che dicono «qui prima o
        poi ci va qualcosa». L'asset vero è `assets/images/rail-calm.png`,
        disegnato da `scripts/make-rail-image.py` e versionato con il resto:
        nessun URL remoto, nessuna dipendenza che un giorno smette di
        rispondere. Essendo questa la barra condivisa, la card è identica in
        tutte le schermate che la usano.
      */}
      <View style={styles.card}>
        {/*
          L'immagine riempie la card e il testo le sta sopra, appoggiato al
          cielo — come nella reference. Con la foto relegata a una striscia in
          fondo restava uno stacco netto fra il fondo della card e il cielo:
          due superfici invece di una.
        */}
        <Image
          source={require('@/assets/images/rail-calm.png')}
          //     LA MISURA VA DETTA, NON DEDOTTA.
          // Con il solo `absoluteFill` l'immagine restava larga quanto il file
          // (760x700) e la card, che taglia, ne mostrava l'angolo in alto a
          // sinistra: tutto cielo, nessuna montagna.
          // `objectFit` esplicito perché sul web `resizeMode` da solo lasciava
          // «fill», cioè l'immagine schiacciata dentro il riquadro.
          style={[StyleSheet.absoluteFill, { width: '100%', height: '100%', objectFit: 'cover' }]}
          resizeMode="cover"
          accessibilityIgnoresInvertColors
          accessible
          accessibilityLabel="Creste di montagna nella foschia"
          testID="rail-card-image"
        />
        <Text style={[styles.cardTitle, { color: ora.ink }]}>Una vita più semplice, insieme.</Text>
        <Text style={[styles.cardBody, { color: ora.ink2 }]}>ORA ti accompagna ogni giorno.</Text>
      </View>

      <Pressable
        onPress={() => go(AMBIENT_ACCOUNT_ITEM.route as 'profilo')}
        accessibilityRole="button"
        accessibilityLabel={`Profilo e account di ${nome}`}
        testID="rail-account"
        style={({ pressed }) => [
          styles.account,
          active === 'profilo' && { backgroundColor: ora.activeBg },
          pressed && { opacity: 0.75 },
        ]}
      >
        <Avatar name={nome} picture={user?.picture} size={40} />
        <View style={{ flex: 1 }}>
          <Text style={[styles.accountName, { color: ora.ink }]} numberOfLines={1}>
            {nome.split(/\s+/)[0]}
          </Text>
          <Text style={[styles.accountSub, { color: ora.ink3 }]}>Il tuo piano</Text>
        </View>
        <Ionicons name="chevron-forward" size={18} color={colors.textTertiary} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  rail: {
    width: AMBIENT_RAIL_WIDTH,
    alignSelf: 'stretch',
    borderRightWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: 20,
    //     LA BARRA CI STA TUTTA, SEMPRE. NIENTE SCORRIMENTO.
    // Una barra di navigazione che scorre è una barra che nasconde qualcosa:
    // ci sta tutto perché le voci tengono la loro altezza e la card prende
    // quello che resta, non un pixel di più.
    overflow: 'hidden',
  },
  brand: { paddingHorizontal: 12, paddingBottom: 36, gap: 6 },
  motto: { fontSize: 14, letterSpacing: 0.1 },
  // La lista tiene la sua altezza: sono voci di navigazione, non spazio da
  // comprimere. È la card sotto a prendersi lo spazio che avanza.
  items: { gap: 6, flexShrink: 0 },
  item: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
    minHeight: 46,
    paddingHorizontal: 14,
    borderRadius: 12,
  },
  label: { fontSize: 16 },
  card: {
    // Sta in fondo quando c'è spazio, e scorre con il resto quando non ce n'è.
    marginTop: 'auto',
    borderRadius: 16,
    padding: 20,
    // Quanto basta perché sotto il testo si veda il paesaggio, e non di più:
    // è lei a cedere spazio quando la finestra è bassa, non le voci del menu.
    minHeight: 168,
    flexShrink: 1,
    overflow: 'hidden',
    marginBottom: 22,
    backgroundColor: ora.surfaceWarm,
  },
  cardTitle: { fontSize: 17, fontWeight: '600', lineHeight: 23 },
  cardBody: { fontSize: 14, lineHeight: 20, marginTop: 8 },
  account: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 8,
    paddingVertical: 8,
    borderRadius: 12,
  },
  accountName: { fontSize: 16, fontWeight: '600' },
  accountSub: { fontSize: 13, marginTop: 1 },
});
