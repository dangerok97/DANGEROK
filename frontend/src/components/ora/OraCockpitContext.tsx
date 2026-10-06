import { useCallback, useEffect, useState } from 'react';
import { AppState, Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import { api, type HomeV2Response } from '@/src/api/client';
import type { KnowledgeMap, KnowledgeStar } from './presence/knowledge';
import { presencePalette as palette, presenceColors } from '@/src/theme/presence';
import { tokens } from '@/src/theme/tokens';

type CockpitData = {
  home: HomeV2Response | null;
  knowledge: KnowledgeMap | null;
};

export function OraCockpitContext() {
  const router = useRouter();
  const [data, setData] = useState<CockpitData>({ home: null, knowledge: null });
  const [error, setError] = useState(false);

  const refresh = useCallback(async () => {
    const [home, knowledge] = await Promise.all([
      api.getHome().catch(() => null),
      api.knowledgeMap().catch(() => null),
    ]);
    setData({ home, knowledge });
    setError(!home && !knowledge);
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => {
      if (AppState.currentState === 'active') void refresh();
    }, 30000);
    const app = AppState.addEventListener('change', state => {
      if (state === 'active') void refresh();
    });
    return () => { clearInterval(timer); app.remove(); };
  }, [refresh]);

  const temporary = (data.knowledge?.stars || []).filter((star) => star.temporary);
  const primaryTemp: KnowledgeStar | null = temporary[0] || null;
  const focus = data.home?.primary_focus || null;
  const situation = data.home?.current_situation || null;
  const weather = data.home?.weather?.available ? data.home.weather : null;

  return (
    <View style={styles.rail} testID="ora-cockpit-context">
      <View style={styles.railHead}>
        <View style={styles.liveDot} />
        <Text style={styles.eyebrow}>ORA · CONTESTO</Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Aggiorna contesto"
          onPress={() => void refresh()}
          style={({ pressed }) => [styles.refresh, pressed && styles.pressed]}
        >
          <Ionicons name="refresh-outline" size={16} color={palette.muted} />
        </Pressable>
      </View>

      {primaryTemp ? (
        <View style={[styles.card, styles.tempCard]} testID="ora-cockpit-temporary">
          <View style={styles.cardHead}>
            <View style={styles.tempIcon}>
              <Ionicons name="flash-outline" size={18} color="#ff7373" />
            </View>
            <View style={styles.cardTitleCol}>
              <Text style={styles.tempTitle}>MEMORIA TEMPORANEA</Text>
              <Text style={styles.cardMeta}>
                {temporary.length === 1 ? '1 situazione attiva' : `${temporary.length} situazioni attive`}
              </Text>
            </View>
          </View>
          <Text style={styles.cardText}>{primaryTemp.statement}</Text>
          <Text style={styles.tempHint}>
            La stella rossa sparisce quando questa situazione viene risolta.
          </Text>
        </View>
      ) : null}

      {focus ? (
        <View style={styles.card}>
          <View style={styles.cardHead}>
            <Ionicons name="locate-outline" size={19} color={palette.label} />
            <Text style={styles.cardLabel}>COSA CONTA ORA</Text>
          </View>
          <Text style={styles.cardTitle}>{focus.title}</Text>
          {focus.subtitle || focus.description ? (
            <Text style={styles.cardText} numberOfLines={4}>
              {focus.subtitle || focus.description}
            </Text>
          ) : null}
          <Pressable
            onPress={() => router.push('/situazione' as any)}
            style={({ pressed }) => [styles.linkButton, pressed && styles.pressed]}
            accessibilityRole="button"
          >
            <Text style={styles.linkText}>Apri situazione</Text>
            <Ionicons name="arrow-forward" size={14} color={palette.label} />
          </Pressable>
        </View>
      ) : null}

      {situation?.next_commitment ? (
        <View style={styles.card}>
          <View style={styles.cardHead}>
            <Ionicons name="time-outline" size={19} color={palette.label} />
            <Text style={styles.cardLabel}>PROSSIMO PASSO</Text>
          </View>
          <Text style={styles.cardText}>{String(situation.next_commitment)}</Text>
        </View>
      ) : null}

      {weather ? (
        <View style={styles.card}>
          <View style={styles.cardHead}>
            <Ionicons name="partly-sunny-outline" size={19} color={palette.label} />
            <Text style={styles.cardLabel}>METEO LIVE</Text>
          </View>
          <Text style={styles.cardTitle}>
            {[weather.label, typeof weather.temperature_c === 'number' ? `${weather.temperature_c}°C` : null]
              .filter(Boolean)
              .join(' · ')}
          </Text>
          {weather.place ? <Text style={styles.cardMeta}>{weather.place}</Text> : null}
        </View>
      ) : null}

      {!primaryTemp && !focus && !situation?.next_commitment && !weather ? (
        <View style={styles.empty}>
          <Ionicons name={error ? 'cloud-offline-outline' : 'sparkles-outline'} size={20} color={palette.muted} />
          <Text style={styles.emptyText}>
            {error ? 'Contesto non disponibile.' : 'Nessun contesto urgente. ORA resta in ascolto.'}
          </Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  rail: {
    width: '100%',
    gap: 12,
  },
  railHead: {
    minHeight: 42,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 4,
  },
  liveDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: palette.label,
    shadowColor: palette.label,
    shadowOpacity: 0.9,
    shadowRadius: 8,
  },
  eyebrow: {
    flex: 1,
    color: palette.muted,
    fontSize: 11,
    letterSpacing: 1.6,
    fontWeight: '700',
  },
  refresh: {
    width: tokens.touch.min,
    height: tokens.touch.min,
    borderRadius: tokens.touch.min / 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  card: {
    gap: 9,
    padding: 16,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: palette.border,
    borderRadius: 18,
    backgroundColor: 'rgba(12,21,30,.78)',
  },
  tempCard: {
    borderColor: 'rgba(255,92,92,.42)',
    backgroundColor: 'rgba(44,12,18,.38)',
  },
  cardHead: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
  },
  tempIcon: {
    width: 34,
    height: 34,
    borderRadius: 17,
    borderWidth: 1,
    borderColor: 'rgba(255,92,92,.55)',
    backgroundColor: 'rgba(255,92,92,.08)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  cardTitleCol: { flex: 1, gap: 2 },
  cardLabel: {
    color: palette.muted,
    fontSize: 10,
    letterSpacing: 1.2,
    fontWeight: '700',
  },
  tempTitle: {
    color: '#ff7373',
    fontSize: 11,
    letterSpacing: 1.1,
    fontWeight: '800',
  },
  cardTitle: {
    color: presenceColors.textPrimary,
    fontSize: 15,
    lineHeight: 20,
    fontWeight: '650' as any,
  },
  cardText: {
    color: presenceColors.textSecondary,
    fontSize: 13,
    lineHeight: 19,
  },
  cardMeta: {
    color: palette.muted,
    fontSize: 11,
    lineHeight: 16,
  },
  tempHint: {
    color: '#df9c9c',
    fontSize: 11,
    lineHeight: 16,
  },
  linkButton: {
    minHeight: 38,
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 10,
    borderRadius: 10,
    backgroundColor: 'rgba(159,206,217,.08)',
  },
  linkText: {
    color: palette.label,
    fontSize: 12,
    fontWeight: '600',
  },
  empty: {
    minHeight: 120,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: palette.border,
    borderRadius: 18,
    backgroundColor: 'rgba(12,21,30,.45)',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    padding: 18,
  },
  emptyText: {
    color: palette.muted,
    fontSize: 12,
    lineHeight: 18,
    textAlign: 'center',
  },
  pressed: { opacity: 0.7 },
});
