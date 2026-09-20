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
import { Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
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
        stessa frase della reference. Il paesaggio è disegnato, non una foto.
      */}
      <LinearGradient
        colors={['#DCE6F2', '#EEF1F4', '#F7F1E8']}
        start={{ x: 0, y: 0 }}
        end={{ x: 0, y: 1 }}
        style={styles.card}
      >
        <Text style={[styles.cardTitle, { color: ora.ink }]}>Una vita più semplice, insieme.</Text>
        <Text style={[styles.cardBody, { color: ora.ink2 }]}>ORA ti accompagna ogni giorno.</Text>
        <View style={styles.hills} pointerEvents="none">
          <View style={[styles.hill, styles.hillBack]} />
          <View style={[styles.hill, styles.hillFront]} />
        </View>
      </LinearGradient>

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
  },
  brand: { paddingHorizontal: 12, paddingBottom: 36, gap: 6 },
  motto: { fontSize: 14, letterSpacing: 0.1 },
  items: { flex: 1, gap: 6 },
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
    borderRadius: 16,
    padding: 20,
    paddingBottom: 88,
    overflow: 'hidden',
    marginBottom: 22,
  },
  cardTitle: { fontSize: 17, fontWeight: '600', lineHeight: 23 },
  cardBody: { fontSize: 14, lineHeight: 20, marginTop: 8 },
  hills: { position: 'absolute', left: 0, right: 0, bottom: 0, height: 78 },
  hill: { position: 'absolute', borderTopLeftRadius: 400, borderTopRightRadius: 400 },
  hillBack: {
    left: -40, right: 40, bottom: -10, height: 70,
    backgroundColor: '#C9D3DE',
  },
  hillFront: {
    left: 60, right: -60, bottom: -24, height: 64,
    backgroundColor: '#B7C3D1',
  },
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
