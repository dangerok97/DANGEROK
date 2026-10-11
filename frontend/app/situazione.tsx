import { useCallback, useRef, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable, RefreshControl, ActivityIndicator } from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

import { tokens } from '@/src/theme/tokens';
import { api, HomeSituationResponse } from '@/src/api/client';
import type { KnowledgeStar } from '@/src/components/ora/presence/knowledge';
import { PrioritaList } from '@/src/components/home/v2/PrioritaList';
import { SituazioneCard } from '@/src/components/home/v2/SituazioneCard';
import { SituationDetails, SituationOutcomeSummary } from '@/src/components/ora/SituationOutcomeSummary';

const outcomeColors = {
  text: tokens.color.onSurface, secondary: tokens.color.onSurfaceMuted, attention: tokens.color.warning,
};

/** Real full-situation view opened from Home CTA. */
export default function SituazioneScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [data, setData] = useState<HomeSituationResponse | null>(null);
  const [temporaries, setTemporaries] = useState<KnowledgeStar[] | null>(null);
  const [temporaryError, setTemporaryError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestVersion = useRef(0);

  const load = useCallback(async () => {
    const version = ++requestVersion.current;
    const current = () => version === requestVersion.current;
    setError(null);
    setTemporaryError(null);
    // These are independent projections. A slow or unavailable summary must
    // not hide temporary Situations, and an older refresh cannot replace a
    // newer result after navigation or a pull-to-refresh.
    await Promise.allSettled([
      api.getHomeSituation().then((result) => {
        if (current()) setData(result);
      }).catch((e) => {
        if (current()) setError(e?.message || 'Impossibile caricare il riepilogo della giornata.');
      }),
      api.knowledgeMap().then((map) => {
        if (current()) setTemporaries((map.stars || []).filter((item) => item.temporary));
      }).catch(() => {
        if (current()) {
          setTemporaries(null);
          setTemporaryError('Non riesco ad aggiornare le situazioni temporanee. Riprova.');
        }
      }),
    ]);
    if (current()) {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(useCallback(() => {
    setLoading(true);
    void load();
    return () => { requestVersion.current += 1; };
  }, [load]));

  return (
    <SafeAreaView style={styles.safe} edges={['top']} testID="situazione-screen">
      <View style={styles.topBar}>
        <Pressable onPress={() => router.back()} accessibilityRole="button" accessibilityLabel="Indietro" testID="situazione-back" hitSlop={12}>
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
            onRefresh={() => { setRefreshing(true); void load(); }}
            tintColor={tokens.color.onSurface}
          />
        }
      >
        {loading ? <ActivityIndicator color={tokens.color.onSurface} /> : null}
        {error ? <Text style={styles.error}>{error}</Text> : null}
        {data?.current_situation ? (
          <SituazioneCard situation={{ ...data.current_situation, cta_label: 'Aggiorna', cta_route: '/situazione' }} onOpen={load} />
        ) : null}
        <View style={styles.temporarySection} testID="situazione-temporary-section">
          <Text style={styles.temporaryHeading}>Situazioni temporanee</Text>
          {temporaryError ? (
            <View style={styles.temporaryCard}>
              <Text style={styles.error}>{temporaryError}</Text>
              <Pressable accessibilityRole="button" accessibilityLabel="Ricarica le situazioni temporanee"
                onPress={() => { void load(); }} style={styles.temporaryLink}>
                <Text style={styles.temporaryLinkLabel}>Riprova</Text>
              </Pressable>
            </View>
          ) : temporaries === null ? (
            <Text style={styles.temporaryCaption}>Sto aggiornando le situazioni da seguire…</Text>
          ) : temporaries.length ? temporaries.map((star) => {
            const followup = star.follow_up;
            const confirmed = ['scheduled', 'due', 'running'].includes(followup?.status || '');
            const checked = followup?.last_checked_at ? new Date(followup.last_checked_at) : null;
            const title = star.semantic_kind || 'Situazione da seguire';
            return (
              <View key={star.situation_id || star.id} style={styles.temporaryCard}
                testID={`situazione-temporary-${star.situation_id || star.id}`}>
                <Text style={styles.temporaryTitle}>{title}</Text>
                <SituationOutcomeSummary
                  outcome={followup?.outcome}
                  desiredOutcome={followup?.desired_outcome || star.desired_outcome}
                  situationRevision={star.situation_revision}
                  followupStatus={followup?.status}
                  colors={outcomeColors}
                  testID={`situazione-outcome-${star.situation_id || star.id}`}
                />
                <SituationDetails colors={outcomeColors}>
                  <Text style={styles.temporaryText}>{star.current_state_summary || star.statement}</Text>
                  {star.location_label ? (
                    <Text style={styles.temporaryCaption}>Luogo: {star.location_label}</Text>
                  ) : null}
                  {star.expected_outcome_summary ? (
                    <Text style={styles.temporaryCaption}>Esito atteso registrato: {star.expected_outcome_summary}</Text>
                  ) : null}
                  <Text style={[styles.temporaryStatus, {
                    color: confirmed || followup?.status === 'review_pending'
                      ? tokens.color.onSurface : tokens.color.warning,
                  }]}>
                    {confirmed && followup?.next_check_label
                      ? `Prossimo controllo: ${followup.next_check_label}`
                      : followup?.diagnosis || (followup?.status === 'review_pending'
                        ? 'ORA ha preso in carico la valutazione. Il primo controllo non è ancora programmato.'
                        : 'Controllo automatico non confermato.')}
                  </Text>
                  {checked && !Number.isNaN(checked.getTime()) ? (
                    <Text style={styles.temporaryCaption}>
                      Ultima verifica registrata: {checked.toLocaleString('it-IT', { timeZone: followup?.timezone || undefined })}
                    </Text>
                  ) : null}
                  {followup?.last_result ? (
                    <Text style={styles.temporaryCaption}>Esito dell’ultima verifica: {followup.last_result}</Text>
                  ) : null}
                </SituationDetails>
                <Pressable accessibilityRole="button" accessibilityLabel={`Apri ORA per ${title}`}
                  testID={`open-temporary-${star.situation_id || star.id}`}
                  onPress={() => router.push(followup?.goal_id
                    ? { pathname: '/ora', params: { goalId: followup.goal_id, entry: 'agent_need' } }
                    : '/ora')}
                  style={styles.temporaryLink}>
                  <Text style={styles.temporaryLinkLabel}>{followup?.goal_id ? 'Apri il lavoro di ORA' : 'Apri ORA'}</Text>
                  <Ionicons name="chevron-forward" size={16} color={tokens.color.onSurface} />
                </Pressable>
              </View>
            );
          }) : (
            <Text style={styles.temporaryCaption}>Nessuna situazione temporanea attiva in ORA.</Text>
          )}
        </View>
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
    padding: tokens.spacing.lg, borderWidth: 1, borderColor: tokens.color.border,
    backgroundColor: tokens.color.surfaceSecondary, borderRadius: tokens.radius.lg, gap: 8,
  },
  temporaryTitle: { fontSize: 16, fontWeight: '700', color: tokens.color.onSurface },
  temporaryText: { fontSize: 15, lineHeight: 22, color: tokens.color.onSurface },
  temporaryStatus: { fontSize: 13, lineHeight: 19, fontWeight: '600' },
  temporaryCaption: { fontSize: 13, lineHeight: 19, color: tokens.color.onSurfaceMuted },
  temporaryLink: { flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 4, minHeight: 44 },
  temporaryLinkLabel: { color: tokens.color.onSurface, fontSize: 14, fontWeight: '600' },
});
