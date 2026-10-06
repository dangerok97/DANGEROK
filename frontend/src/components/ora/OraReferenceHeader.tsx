import { useEffect, useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import { api, type HomeV2Response } from '@/src/api/client';
import { OraBrand } from '@/src/shell/OraBrand';
import { presencePalette as palette, presenceColors } from '@/src/theme/presence';

const NAV = [
  { label: 'Home', icon: 'home-outline' as const, href: '/' },
  { label: 'Vita', icon: 'layers-outline' as const, href: '/vita' },
  { label: 'Calendario', icon: 'calendar-outline' as const, href: '/manage-calendars' },
  { label: 'Luoghi', icon: 'location-outline' as const, href: '/luoghi' },
  { label: 'Mappa', icon: 'map-outline' as const, href: null },
  { label: 'Impostazioni', icon: 'settings-outline' as const, href: '/settings' },
];

function clockLabel(now: Date): string {
  return now.toLocaleString('it-IT', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function OraReferenceHeader() {
  const router = useRouter();
  const [now, setNow] = useState(() => new Date());
  const [home, setHome] = useState<HomeV2Response | null>(null);

  useEffect(() => {
    const tick = setInterval(() => setNow(new Date()), 30000);
    const weather = setInterval(() => {
      void api.getHome().then(setHome).catch(() => {});
    }, 60000);
    void api.getHome().then(setHome).catch(() => {});
    return () => {
      clearInterval(tick);
      clearInterval(weather);
    };
  }, []);

  const weather = home?.weather?.available ? home.weather : null;
  const weatherText = useMemo(
    () => [
      typeof weather?.temperature_c === 'number' ? `${weather.temperature_c}°C` : null,
      weather?.place || null,
    ].filter(Boolean),
    [weather],
  );

  return (
    <View style={styles.root} testID="ora-reference-header">
      <View style={styles.brand}>
        <OraBrand size={34} />
        <Text style={styles.tagline}>IL TUO ASSISTENTE PERSONALE</Text>
      </View>

      <View style={styles.nav}>
        {NAV.map((item) => {
          const active = item.label === 'Mappa';
          return (
            <Pressable
              key={item.label}
              accessibilityRole="tab"
              accessibilityState={{ selected: active }}
              onPress={() => item.href && router.push(item.href as any)}
              style={({ pressed }) => [styles.navItem, active && styles.navItemActive, pressed && styles.pressed]}
            >
              <Ionicons name={item.icon} size={20} color={active ? '#8bdfff' : '#9db8c7'} />
              <Text style={[styles.navLabel, active && styles.navLabelActive]}>{item.label}</Text>
            </Pressable>
          );
        })}
      </View>

      <View style={styles.right}>
        <View style={styles.clockPill}>
          <Text style={styles.clock}>{clockLabel(now)}</Text>
        </View>
        <View style={styles.weather}>
          <Ionicons
            name={weather && /piogg|tempor/i.test(String(weather.label || '')) ? 'rainy-outline' : 'partly-sunny-outline'}
            size={28}
            color="#89dfff"
          />
          <View style={styles.weatherCopy}>
            {weatherText.map((line, index) => <Text key={index} style={index === 0 ? styles.weatherTemp : styles.weatherPlace}>{line}</Text>)}
          </View>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    height: 112,
    flexShrink: 0,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 28,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: 'rgba(133,195,214,.10)',
    backgroundColor: presencePalette.background,
  },
  brand: { width: 300, gap: 2, justifyContent: 'center' },
  tagline: { color: '#55a8cc', fontSize: 11, letterSpacing: 1.4, marginLeft: 2 },
  nav: { flex: 1, flexDirection: 'row', justifyContent: 'center', alignSelf: 'stretch', gap: 18 },
  navItem: {
    minWidth: 76, paddingHorizontal: 6, alignItems: 'center', justifyContent: 'center',
    gap: 5, borderBottomWidth: 2, borderBottomColor: 'transparent',
  },
  navItemActive: { borderBottomColor: '#8bdfff' },
  navLabel: { color: '#9db8c7', fontSize: 12 },
  navLabelActive: { color: '#c7f2ff', fontWeight: '700' },
  right: { width: 300, flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: 16 },
  clockPill: {
    minHeight: 42, justifyContent: 'center', paddingHorizontal: 18, borderRadius: 22,
    borderWidth: StyleSheet.hairlineWidth, borderColor: 'rgba(121,190,216,.28)',
    backgroundColor: 'rgba(8,18,27,.55)',
  },
  clock: { color: '#bcd0dc', fontSize: 12 },
  weather: { minWidth: 105, flexDirection: 'row', alignItems: 'center', gap: 8 },
  weatherCopy: { gap: 1 },
  weatherTemp: { color: palette.text, fontSize: 15 },
  weatherPlace: { color: palette.muted, fontSize: 11 },
  pressed: { opacity: .7 },
});
