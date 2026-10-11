import { useCallback, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable, RefreshControl, ActivityIndicator } from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

import { tokens } from '@/src/theme/tokens';
import { api, HomeSituationResponse } from '@/src/api/client';
import type { KnowledgeStar } from '@/src/components/ora/presence/knowledge';
import { PrioritaList } from '@/src/components/home/v2/PrioritaList';
import { SituazioneCard } from '@/src/components/home/v2/SituazioneCard';

/** Real full-situation view opened from Home CTA. */
export default function SituazioneScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [data, setData] = useState<HomeSituationResponse | null>(null);
  const [temporaries, setTemporaries] = useState<KnowledgeStar[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const r = await api.getHomeSituation();
      setData(r);
      // The day summary is not the owner of temporary Situations. Read the
      // same active Situation projection used by the neural memory map.
      // A slow/unavailable knowledge API must never hide today's priorities.
      void api.knowledgeMap().then((map) => {
        setTemporaries((map.stars || []).filter((item) => item.temporary));
      }).catch(() => setTemporaries(null));
    } catch (e: any) {
      setError(e?.message || 'Impossibile caricare la situazione');
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { setLoading(true); load(); }, [load]));

  return (
    <SafeAreaView style={styles.safe} edges={['top']} testID="situazione-screen">
      <View style={styles.topBar}>
        <Pressable onPress={() => router.back()} accessibilityRole="button" testID="situazione-back" hitSlop={12}>
          <Ionicons name="chevron-back" size={24} color={tokens.color.onSurface} />
        </Pressable>
        <Text style={styles.title} accessibilityRole="header">Situazione completa</Text>
        <View style={{ width: 24 }} />
      </View>
      <ScrollView
        contentContainerStyle={{
          padding: tokens.spacing.lg,
          gap: tokens.spacing.lg,
          paddingBottom: insets.bottom + 40,
          maxWidth: 720,
          width: '100%',
          alignSelf: 'center',
        }}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }}
            tintColor={tokens.color.onSurface}
          />
        }
      >
        {loading ? <ActivityIndicator color={tokens.color.onSurface} /> : null}
        {error ? <Text style={styles.error}>{error}</Text> : null}
        {data?.current_situation ? (
          <SituazioneCard situation={{ ...data.current_situation, cta_label: 'Aggiorna', cta_route: '/situazione' }} onOpen={load} />
        ) : null}
        {temporaries !== null ? (
          <View style={styles.temporarySection} testID="situazione-temporary-section">
            <Text style={styles.temporaryHeading}>Situazioni temporanee</Text>
            {temporaries.length ? temporaries.slice(0, 8).map((star) => {
              const followup = star.follow_up;
              const realAlarm = ['scheduled', 'due', 'running'].includes(followup?.status || '');
              return (
                <View key={star.situation_id || star.id} style={styles.temporaryCard}
                  testID={`situazione-temporary-${star.situation_id || star.id}`}>
                  <Text style={styles.temporaryTitle}>
                    {star.semantic_kind || star.title || 'Situazione da seguire'}
                  </Text>
                  <Text style={styles.temporaryText}>
                    {star.current_state_summary || star.statement}
                  </Text>
                  {star.expected_outcome_summary ? (
                    <Text style={styles.temporaryCaption}>
                      Esito atteso: {star.expected_outcome_summary}
                    </Text>
                  ) : null}
                  <Text style={[styles.temporaryStatus, { color: realAlarm ? tokens.color.onSurface : tokens.color.warning }]}>
                    {realAlarm && followup?.next_check_label
                      ? `Prossimo controllo: ${followup.next_check_label}`
                      : followup?.diagnosis || 'Controllo automatico non confermato.'}
                  </Text>
                  {followup?.last_checked_at ? (
                    <Text style={styles.temporaryCaption}>
                      Ultima verifica registrata: {new Date(followup.last_checked_at).toLocaleString('it-IT')}
                    </Text>
                  ) : null}
                  {followup?.last_result ? (
                    <Text style={styles.temporaryCaption}>
                      Esito dell’ultima verifica: {followup.last_result}
                    </Text>
                  ) : null}
                  <Pressable accessibilityRole="button"
                    testID={`open-temporary-${star.situation_id || star.id}`}
                    onPress={() => router.push('/ora')}
                    style={styles.temporaryLink}>
                    <Text style={styles.temporaryLinkLabel}>Apri nella memoria temporanea</Text>
                    <Ionicons name="chevron-forward" size={16} color={tokens.color.onSurface} />
                  </Pressable>
                </View>
              );
            }) : (
              <Text style={styles.temporaryCaption}>
                Nessuna situazione temporanea attiva in ORA.
              </Text>
            )}
          </View>
        ) : null}
        {data?.primary_focus ? (
          <View style={styles.focusBox}>
            <Text style={styles.focusLabel}>Focus attuale</Text>
            <Text style={styles.focusTitle}>{data.primary_focus.title}</Text>
            {data.primary_focus.reason_summary ? (
              <Text style={styles.focusReason}>{data.primary_focus.reason_summary}</Text>
            ) : null}
          </View>
        ) : null}
        {data?.priorities ? <PrioritaList groups={data.priorities} /> : null}
        {data?.connection_warnings?.length ? (
          <View style={styles.warns}>
            {data.connection_warnings.map((w) => (
              <Text key={w.code} style={styles.warnText}>{w.message}</Text>
            ))}
          </View>
        ) : null}
        {data ? (
          <Text style={styles.meta}>
            {data.ranking_version} · {new Date(data.generated_at).toLocaleString('it-IT')}
          </Text>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: tokens.color.surface },
  topBar: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: tokens.spacing.lg, paddingVertical: tokens.spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: tokens.color.border,
  },
  title: { fontSize: 17, fontWeight: '700', color: tokens.color.onSurface },
  error: { color: tokens.color.error, fontSize: 14 },
  focusBox: {
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: tokens.radius.lg,
    padding: tokens.spacing.lg,
    gap: 6,
    borderWidth: 1,
    borderColor: tokens.color.border,
  },
  focusLabel: { fontSize: 12, color: tokens.color.onSurfaceMuted, fontWeight: '600', textTransform: 'uppercase' },
  focusTitle: { fontSize: 18, fontWeight: '700', color: tokens.color.onSurface },
  focusReason: { fontSize: 13, color: tokens.color.onSurfaceMuted, lineHeight: 18 },
  warns: { gap: 6 },
  warnText: { fontSize: 13, color: tokens.color.warning },
  meta: { fontSize: 11, color: tokens.color.onSurfaceDim },
  temporarySection: { gap: tokens.spacing.sm },
  temporaryHeading: { fontSize: 16, fontWeight: '700', color: tokens.color.onSurface },
  temporaryCard: {
    padding: tokens.spacing.md, borderWidth: 1, borderColor: tokens.color.border,
    backgroundColor: tokens.color.surfaceSecondary, borderRadius: tokens.radius.lg, gap: 8,
  },
  temporaryTitle: { fontSize: 15, fontWeight: '700', color: tokens.color.onSurface },
  temporaryText: { fontSize: 13, lineHeight: 19, color: tokens.color.onSurface },
  temporaryStatus: { fontSize: 12, lineHeight: 18, fontWeight: '600' },
  temporaryCaption: { fontSize: 12, lineHeight: 18, color: tokens.color.onSurfaceMuted },
  temporaryLink: { flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 6, minHeight: 36 },
  temporaryLinkLabel: { color: tokens.color.onSurface, fontSize: 12, fontWeight: '600' },
});
