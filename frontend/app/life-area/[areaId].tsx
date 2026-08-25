/**
 * One part of a life, opened.
 *
 * The chevron on a Vita card has to lead somewhere real, and what a person
 * needs here is narrow: what ORA holds about this part of their life, where
 * each thing came from, and how to fix it if it is wrong. That is a page of
 * sentences, not an inspector — no ids, no scores, no store vocabulary, and
 * nothing that would let someone edit the record directly. Corrections run
 * through the clarification loop and through ORA, the two governed paths that
 * already exist.
 *
 * Presentation only: it reads the same two payloads Vita reads and shows the
 * slice belonging to one area.
 */
import { useCallback, useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

import { api } from '@/src/api/client';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { humanizeError } from '@/src/utils/errors';
import { buildOraConversationHref } from '@/src/ora/oraNav';
import { mapFromLifeMapApi } from '@/src/components/contexts/quiet';
import { buildVita, VitaSkeleton, type VitaArea } from '@/src/components/vita';

const READING_MAX_WIDTH = 720;

export default function LifeAreaScreen() {
  const { areaId } = useLocalSearchParams<{ areaId: string }>();
  const router = useRouter();
  const { colors } = useTheme();

  const [area, setArea] = useState<VitaArea | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const domain = String(areaId || '').toLowerCase();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [map, memory] = await Promise.all([
        api.getLifeMap(),
        api.getLifeMemory().catch(() => null),
      ]);
      const model = buildVita(mapFromLifeMapApi(map as any), memory as any);
      setArea(model.areas.find((a) => a.domain.toLowerCase() === domain) || null);
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
    } finally {
      setLoading(false);
    }
  }, [domain]);

  useEffect(() => {
    void load();
  }, [load]);

  const goBack = useCallback(() => {
    if (router.canGoBack?.()) router.back();
    else router.replace('/contesti' as any);
  }, [router]);

  const correctWithOra = useCallback(
    () => router.push(buildOraConversationHref({ entryPoint: 'vita' }) as any),
    [router],
  );

  return (
    <SafeAreaView
      edges={['top']}
      style={[styles.root, { backgroundColor: colors.backgroundPrimary }]}
      testID="life-area-screen"
    >
      <ScrollView
        contentContainerStyle={styles.scroll}
        showsVerticalScrollIndicator={false}
        testID="life-area-scroll"
      >
        <View style={styles.column}>
          <View style={styles.head}>
            <Pressable
              onPress={goBack}
              hitSlop={8}
              style={({ pressed }) => [styles.back, pressed && styles.pressed]}
              accessibilityRole="button"
              accessibilityLabel="Indietro"
              testID="life-area-back"
            >
              <Ionicons name="chevron-back" size={22} color={colors.textSecondary} />
            </Pressable>
            <Text style={[styles.eyebrow, { color: colors.textTertiary }]}>VITA</Text>
          </View>

          {loading ? (
            <VitaSkeleton wide={false} />
          ) : error ? (
            <View style={[styles.panel, { backgroundColor: colors.surface, borderColor: colors.border }]}>
              <Text style={[styles.body, { color: colors.textPrimary }]}>{error}</Text>
              <Pressable
                onPress={() => void load()}
                style={({ pressed }) => [styles.ghost, { borderColor: colors.border }, pressed && styles.pressed]}
                accessibilityRole="button"
                testID="life-area-retry"
              >
                <Text style={[styles.ghostLabel, { color: colors.textPrimary }]}>Riprova</Text>
              </Pressable>
            </View>
          ) : !area ? (
            <View style={styles.block} testID="life-area-missing">
              <Text style={[styles.title, { color: colors.textPrimary }]}>
                Questa parte non è più nella tua Vita.
              </Text>
              <Text style={[styles.body, { color: colors.textSecondary }]}>
                Può succedere quando qualcosa cambia. Torna indietro per vedere cosa c'è ora.
              </Text>
            </View>
          ) : (
            <>
              <View style={styles.block}>
                <Text
                  style={[styles.title, { color: colors.textPrimary }]}
                  accessibilityRole="header"
                  aria-level={1}
                >
                  {area.title}
                </Text>
                {area.identity ? (
                  <Text style={[styles.body, { color: colors.textSecondary }]}>
                    {area.identity}
                  </Text>
                ) : null}
              </View>

              {area.facts.length || area.moreCount ? (
                <View style={styles.block}>
                  <Text style={[styles.sectionLabel, { color: colors.textTertiary }]}>
                    COSA ORA TIENE A MENTE
                  </Text>
                  <View
                    style={[
                      styles.panel,
                      { backgroundColor: colors.surface, borderColor: colors.border },
                    ]}
                    testID="life-area-facts"
                  >
                    {area.facts.map((f, i) => (
                      <View
                        key={f.id}
                        style={[
                          styles.factRow,
                          i > 0 && { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.divider },
                        ]}
                      >
                        <Text style={[styles.factText, { color: colors.textPrimary }]}>
                          {f.statement}
                        </Text>
                        <View style={styles.factMeta}>
                          {f.provenance ? (
                            <Text style={[styles.provenance, { color: colors.textTertiary }]}>
                              {f.provenance}
                            </Text>
                          ) : null}
                          {f.uncertain ? (
                            <View style={[styles.uncertain, { borderColor: colors.warning }]}>
                              <Ionicons name="help-circle-outline" size={12} color={colors.warning} />
                              <Text style={[styles.uncertainLabel, { color: colors.warning }]}>
                                ORA non ne è sicura
                              </Text>
                            </View>
                          ) : null}
                        </View>
                      </View>
                    ))}
                  </View>
                  {area.moreCount > 0 ? (
                    <Text style={[styles.more, { color: colors.textTertiary }]}>
                      {area.moreCount === 1
                        ? 'ORA tiene a mente un’altra cosa su questa parte della tua vita.'
                        : `ORA tiene a mente altre ${area.moreCount} cose su questa parte della tua vita.`}
                    </Text>
                  ) : null}
                </View>
              ) : (
                <Text style={[styles.body, { color: colors.textSecondary }]} testID="life-area-nothing">
                  ORA non ha ancora imparato molto su questa parte della tua vita.
                </Text>
              )}

              <Pressable
                onPress={correctWithOra}
                style={({ pressed }) => [
                  styles.primary,
                  { backgroundColor: colors.accent },
                  pressed && styles.pressed,
                ]}
                accessibilityRole="button"
                testID="life-area-correct"
              >
                <Text style={[styles.primaryLabel, { color: colors.onAccent }]}>
                  Correggi o aggiorna con ORA
                </Text>
              </Pressable>
            </>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  scroll: { flexGrow: 1, paddingHorizontal: tokens.spacing.xl, paddingTop: tokens.spacing.sm, paddingBottom: tokens.spacing.xxxl },
  column: { width: '100%', maxWidth: READING_MAX_WIDTH, alignSelf: 'center', gap: tokens.spacing.xl },
  head: { flexDirection: 'row', alignItems: 'center', gap: 2 },
  back: {
    width: tokens.touch.min, height: tokens.touch.min,
    alignItems: 'center', justifyContent: 'center', marginLeft: -12,
  },
  eyebrow: { fontSize: 11, fontWeight: '700', letterSpacing: 1.3 },
  block: { gap: tokens.spacing.sm },
  title: { fontSize: 26, fontWeight: '700', letterSpacing: -0.6, lineHeight: 33 },
  sectionLabel: { fontSize: 11, fontWeight: '700', letterSpacing: 1.2 },
  body: { fontSize: 15, lineHeight: 22 },
  panel: {
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: tokens.spacing.lg,
    gap: tokens.spacing.sm,
  },
  factRow: { paddingVertical: tokens.spacing.md, gap: 4 },
  factText: { fontSize: 15, lineHeight: 22 },
  factMeta: { flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.md, flexWrap: 'wrap' },
  provenance: { fontSize: 12 },
  uncertain: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    borderWidth: StyleSheet.hairlineWidth, borderRadius: tokens.radius.sm,
    paddingHorizontal: 6, paddingVertical: 2,
  },
  uncertainLabel: { fontSize: 11, fontWeight: '600' },
  more: { fontSize: 13, lineHeight: 19 },
  primary: {
    alignSelf: 'flex-start', minHeight: tokens.touch.min, justifyContent: 'center',
    paddingHorizontal: tokens.spacing.xl, borderRadius: tokens.radius.md,
  },
  primaryLabel: { fontSize: 15, fontWeight: '600' },
  ghost: {
    alignSelf: 'flex-start', minHeight: 40, justifyContent: 'center',
    paddingHorizontal: tokens.spacing.lg, borderRadius: tokens.radius.md,
    borderWidth: StyleSheet.hairlineWidth, marginBottom: tokens.spacing.md,
  },
  ghostLabel: { fontSize: 14, fontWeight: '600' },
  pressed: { opacity: 0.75 },
});
