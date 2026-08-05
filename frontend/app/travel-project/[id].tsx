/**
 * Travel Project detail — period, maps, calendar events, prep, phase.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator, Linking,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

import { tokens } from '@/src/theme/tokens';
import { api, TravelProject } from '@/src/api/client';
import { haptic } from '@/src/utils/haptic';
import { humanizeError } from '@/src/utils/errors';

const PHASE_IT: Record<string, string> = {
  upcoming: 'In programma',
  days_until: 'In arrivo',
  departure_day: 'Partenza oggi',
  during: 'In vacanza',
  welcome_back: 'Bentornato',
};

export default function TravelProjectScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [project, setProject] = useState<TravelProject | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const res = await api.travelProjectGet(id);
      setProject(res.project);
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const openMaps = async () => {
    const url = project?.maps?.deep_link as string | undefined;
    if (!url) return;
    haptic('tap');
    try {
      await Linking.openURL(url);
    } catch {
      setError('Impossibile aprire Maps');
    }
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.safe} testID="travel-project-loading">
        <ActivityIndicator color={tokens.color.onSurface} />
      </SafeAreaView>
    );
  }

  if (!project) {
    return (
      <SafeAreaView style={styles.safe}>
        <Text style={styles.error}>{error || 'Progetto non trovato'}</Text>
        <Pressable onPress={() => router.back()} style={styles.backBtn}>
          <Text style={styles.backText}>Indietro</Text>
        </Pressable>
      </SafeAreaView>
    );
  }

  const maps = project.maps || {};
  const advice = project.departure_advice || {};
  const events = project.calendar_events || [];

  return (
    <SafeAreaView style={styles.safe} testID="travel-project">
      <View style={styles.topBar}>
        <Pressable onPress={() => router.back()} hitSlop={12} testID="travel-back">
          <Ionicons name="chevron-back" size={22} color={tokens.color.onSurface} />
        </Pressable>
        <Text style={styles.kicker}>VIAGGIO</Text>
        <View style={{ width: 22 }} />
      </View>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.title} accessibilityRole="header">{project.title}</Text>
        <Text style={styles.phase} testID="travel-phase">
          {PHASE_IT[project.phase || ''] || project.phase}
          {project.days_until != null && project.days_until >= 0
            ? ` · tra ${project.days_until}g`
            : ''}
        </Text>
        <Text style={styles.line}>
          {project.destination}
          {project.departure_place ? ` ← ${project.departure_place}` : ''}
        </Text>
        <Text style={styles.line}>
          {(project.start_date || '').slice(0, 10)} → {(project.end_date || '').slice(0, 10)}
        </Text>
        <Text style={styles.line}>
          {project.transport || '—'} · prenotazioni: {project.bookings || '—'}
          {project.companions ? ` · ${project.companions} pers.` : ''}
        </Text>

        {events.length > 0 ? (
          <View style={styles.block} testID="travel-calendar-events">
            <Text style={styles.blockTitle}>Calendario proposto</Text>
            {events.map((e) => (
              <Text key={String(e.id || e.kind)} style={styles.item}>
                · {String(e.title)}
                {e.google_event_id ? ' ✓ Google' : ''}
              </Text>
            ))}
          </View>
        ) : null}

        <View style={styles.block} testID="travel-maps">
          <Text style={styles.blockTitle}>Maps</Text>
          {maps.distance_km != null ? (
            <Text style={styles.item}>{String(maps.distance_km)} km · {String(maps.duration_label || '')}</Text>
          ) : (
            <Text style={styles.muted}>Distanza non stimata</Text>
          )}
          {maps.honesty ? <Text style={styles.muted}>{String(maps.honesty)}</Text> : null}
          {maps.tolls_note ? <Text style={styles.muted}>{String(maps.tolls_note)}</Text> : null}
          {maps.deep_link ? (
            <Pressable style={styles.cta} onPress={openMaps} testID="travel-open-maps">
              <Text style={styles.ctaText}>Apri Google Maps</Text>
            </Pressable>
          ) : null}
        </View>

        {advice.message ? (
          <View style={styles.block} testID="travel-departure-advice">
            <Text style={styles.blockTitle}>Orario partenza</Text>
            <Text style={styles.item}>{String(advice.message)}</Text>
          </View>
        ) : null}

        {(project.prep_items || []).length > 0 ? (
          <View style={styles.block} testID="travel-prep">
            <Text style={styles.blockTitle}>Preparazione (opzionale)</Text>
            {(project.prep_items || []).map((p) => (
              <Text key={String(p.id)} style={styles.item}>· {String(p.label)}</Text>
            ))}
          </View>
        ) : null}

        <View style={styles.block}>
          <Text style={styles.blockTitle}>Limiti onesti</Text>
          <Text style={styles.muted}>
            Meteo: {(project.weather as any)?.reason || 'non disponibile'}
          </Text>
          <Text style={styles.muted}>
            Email auto-find: {(project.email_search as any)?.status || 'not_implemented'}
          </Text>
        </View>

        {error ? <Text style={styles.error}>{error}</Text> : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: tokens.color.surface },
  topBar: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingVertical: 10,
  },
  kicker: {
    color: tokens.color.onSurfaceMuted, fontSize: 11, letterSpacing: 1.2, fontWeight: '600',
  },
  content: { padding: 20, paddingBottom: 48, gap: 8 },
  title: {
    color: tokens.color.onSurface, fontSize: 26, fontWeight: '700', marginBottom: 4,
  },
  phase: { color: tokens.color.onSurfaceMuted, fontSize: 14, marginBottom: 8 },
  line: { color: tokens.color.onSurface, fontSize: 15 },
  block: { marginTop: 16, gap: 6 },
  blockTitle: {
    color: tokens.color.onSurface, fontSize: 13, fontWeight: '700', letterSpacing: 0.4,
  },
  item: { color: tokens.color.onSurface, fontSize: 14 },
  muted: { color: tokens.color.onSurfaceMuted, fontSize: 12, lineHeight: 18 },
  cta: {
    marginTop: 8, backgroundColor: tokens.color.brand, paddingVertical: 12,
    borderRadius: 10, alignItems: 'center',
  },
  ctaText: { color: tokens.color.onBrand, fontWeight: '700', fontSize: 14 },
  error: { color: tokens.color.error, marginTop: 12 },
  backBtn: { padding: 16 },
  backText: { color: tokens.color.onSurface },
});
