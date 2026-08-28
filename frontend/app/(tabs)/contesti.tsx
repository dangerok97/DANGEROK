/**
 * Vita — what ORA knows about this person's life.
 *
 * Home is what needs attention, the Workspace is where a goal gets advanced,
 * ORA is where things get talked through. This is the fourth question: what
 * does ORA actually know about me, what is live right now, and what can I
 * correct? It has to read as a living map of a life — never as an inspector
 * over a memory store, which is what makes the difference between a person
 * feeling accompanied and feeling filed.
 *
 * Composition only. The Life Map decides which parts of a life exist and what
 * is currently happening in them; Life Memory supplies the individual things
 * ORA has learned, already phrased as sentences and already carrying where
 * they came from. Nothing here classifies, scores or invents — and every
 * section disappears rather than pretending, because a page about trust cannot
 * afford a single fabricated row.
 *
 * The route keeps its old file name so no navigation contract moves; the
 * surface is Vita everywhere a person can see.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';

import { api, LifeAreaCompleteness, LifeProfile, StudyPlan, TravelProject } from '@/src/api/client';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { ErrorState } from '@/src/components/ui/ErrorState';
import { Appear, useAmbientInset } from '@/src/shell';
import { isNetworkError, useOnlineStatus } from '@/src/hooks/use-online-status';
import { humanizeError } from '@/src/utils/errors';
import { buildOraConversationHref } from '@/src/ora/oraNav';
import { LifeProfileProgress } from '@/src/components/life-profile/LifeProfileProgress';
import { buildContextsMap, mapFromLifeMapApi } from '@/src/components/contexts/quiet';
import {
  GrowStrip,
  LifeAreaCard,
  QuestionsPanel,
  SituationCard,
  SummaryPanel,
  UpdatesPanel,
  VitaEmpty,
  VitaHeader,
  VitaSection,
  VitaSkeleton,
  WhyItMattersDialog,
  buildVita,
  isVitaEmpty,
  type VitaModel,
  type VitaQuestion,
} from '@/src/components/vita';

const PAGE_MAX_WIDTH = 1320;
const RAIL_WIDTH = 300;
/** Below this the rail has nowhere to sit and the page becomes one column. */
const TWO_COLUMN_MIN = 1100;
/** Below this the situation and area grids stop being grids. */
const GRID_MIN = 720;

const EMPTY: VitaModel = {
  situations: [],
  areas: [],
  questions: [],
  updates: [],
  summary: [],
};

/**
 * Resilience only — never overwrites a valid Life Map payload.
 * Preserved verbatim from the Contesti implementation this replaces.
 */
async function loadFallbackCompose(): Promise<{
  map: ReturnType<typeof buildContextsMap>;
  partial: boolean;
  error: string | null;
  network: boolean;
}> {
  const settled = await Promise.allSettled([
    api.lifeSetupProfile(),
    api.studyPlansList(),
    api.travelProjectsList(),
  ]);

  let profile: LifeProfile | null = null;
  let studyPlans: StudyPlan[] = [];
  let travelProjects: TravelProject[] = [];
  let failures = 0;
  let network = false;

  const [profileRes, studyRes, travelRes] = settled;
  if (profileRes.status === 'fulfilled') profile = profileRes.value.profile ?? null;
  else {
    failures += 1;
    if (isNetworkError(profileRes.reason)) network = true;
  }
  if (studyRes.status === 'fulfilled') studyPlans = studyRes.value.items || [];
  else {
    failures += 1;
    if (isNetworkError(studyRes.reason)) network = true;
  }
  if (travelRes.status === 'fulfilled') travelProjects = travelRes.value.items || [];
  else {
    failures += 1;
    if (isNetworkError(travelRes.reason)) network = true;
  }

  const map = buildContextsMap({ profile, studyPlans, travelProjects });
  if (failures === 3) {
    const reason =
      profileRes.status === 'rejected'
        ? profileRes.reason
        : studyRes.status === 'rejected'
          ? studyRes.reason
          : travelRes.status === 'rejected'
            ? travelRes.reason
            : null;
    return {
      map: { situations: [], areas: [] },
      partial: false,
      error: humanizeError(reason, 'default'),
      network,
    };
  }
  return { map, partial: failures > 0, error: null, network };
}

export default function VitaScreen() {
  const { colors } = useTheme();
  const ambient = useAmbientInset();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const { markOffline, markOnline } = useOnlineStatus();

  const twoColumn = width >= TWO_COLUMN_MIN;
  const grid = width >= GRID_MIN;
  const padH = width < 380 ? tokens.spacing.lg : tokens.spacing.xl;

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [vita, setVita] = useState<VitaModel>(EMPTY);
  const [partial, setPartial] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [whyOpen, setWhyOpen] = useState(false);

  const load = useCallback(
    async (opts?: { silent?: boolean; force?: boolean }) => {
      if (!opts?.silent) setLoading(true);

      // Memory is an enrichment: the page is meaningful without it, so its
      // failure costs facts and questions, never the whole surface.
      const memoryPromise = api
        .getLifeMemory({ force: opts?.force === true })
        .catch(() => null);

      try {
        const lifeMap = await api.getLifeMap({ force: opts?.force === true });
        if (!lifeMap?.ok || !Array.isArray(lifeMap.situations)) {
          throw new Error('life_map_invalid_response');
        }
        markOnline();
        const memory = await memoryPromise;
        setVita(buildVita(mapFromLifeMapApi(lifeMap as any), memory as any));
        setPartial(!memory);
        setError(null);
      } catch (e: any) {
        if (__DEV__) {
          console.warn('[Vita] life-map unavailable → FE compose fallback', e?.status || e?.message || e);
        }
        if (isNetworkError(e)) markOffline();
        const fallback = await loadFallbackCompose();
        if (fallback.network) markOffline();
        else markOnline();
        const memory = await memoryPromise;
        setVita(buildVita(fallback.map as any, memory as any));
        setPartial(fallback.partial || !memory);
        setError(fallback.error);
      }

      setLoading(false);
      setRefreshing(false);
    },
    [markOffline, markOnline],
  );

  useEffect(() => {
    void load();
  }, [load]);

  useFocusEffect(
    useCallback(() => {
      void load({ silent: true });
    }, [load]),
  );

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    void load({ silent: true, force: true });
  }, [load]);

  /** Situations already know where they belong — Vita never invents a route. */
  const openSituation = useCallback(
    (href?: string | null) => {
      if (href) router.push(href as any);
    },
    [router],
  );

  const openArea = useCallback(
    (domain: string) => router.push(`/life-area/${encodeURIComponent(domain)}` as any),
    [router],
  );

  /**
   * Answering a question runs the clarification loop that already exists —
   * a governed mutation through Life Memory, not a direct write from a page.
   */
  const askQuestion = useCallback(
    async (q: VitaQuestion) => {
      try {
        const res = await api.lifeMemoryClarifyStart(q.memoryId);
        if (res?.route) router.push(res.route as any);
        else if (res?.session?.id) router.push(`/memory-clarify/${res.session.id}` as any);
      } catch (e: any) {
        setError(humanizeError(e, 'default'));
      }
    },
    [router],
  );

  /** Updating a life is a conversation, not a form with a fixed set of fields. */
  const updateWithOra = useCallback(
    () => router.push(buildOraConversationHref({ entryPoint: 'vita' }) as any),
    [router],
  );

  /*
    What ORA understands of this life, and where it would help to continue.

    Vita is the page a person comes back to, so this is where the profile lives
    once the first run is over — the same figure, the same areas, one tap back
    into the conversation that fills them. Nothing is fetched twice: it is a
    projection, and reading it costs a request, not a reasoning cycle.
  */
  const [profile, setProfile] = useState<{
    percent: number;
    areas: LifeAreaCompleteness[];
    suggested?: string | null;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.lifeProfileCompleteness();
        if (!cancelled && res?.ok) {
          setProfile({
            percent: res.percent,
            areas: res.areas || [],
            suggested: res.suggested_area_id ?? null,
          });
        }
      } catch {
        // Vita renders without it. A page about trust does not show an error
        // because a progress figure could not be read.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const continueSetup = useCallback(
    (areaId?: string) => {
      router.push(
        areaId ? `/life-setup?resume=1&area=${encodeURIComponent(areaId)}` : '/life-setup?resume=1',
      );
    },
    [router],
  );

  const empty = useMemo(() => isVitaEmpty(vita), [vita]);
  const hasContent = !empty;

  const main = (
    <>
      <VitaSection title="IN QUESTO PERIODO" testID="vita-current">
        {vita.situations.length ? (
          <View style={grid ? styles.grid3 : styles.stack}>
            {vita.situations.slice(0, grid ? 3 : 4).map((s) => (
              <View key={s.id} style={grid ? styles.gridCell : undefined}>
                <SituationCard situation={s} onOpen={() => openSituation(s.href)} />
              </View>
            ))}
          </View>
        ) : null}
      </VitaSection>

      {profile ? (
        <VitaSection title="QUELLO CHE ORA SA DI TE" testID="vita-profile">
          <LifeProfileProgress
            percent={profile.percent}
            areas={profile.areas}
            activeAreaId={profile.suggested}
            onOpenArea={(id) => continueSetup(id)}
          />
        </VitaSection>
      ) : null}

      <VitaSection title="LA TUA VITA" testID="vita-areas">
        {vita.areas.length ? (
          <View style={grid ? styles.grid3 : styles.stack}>
            {vita.areas.map((a) => (
              <View key={a.id} style={grid ? styles.gridCell : undefined}>
                <LifeAreaCard area={a} onOpen={() => openArea(a.domain)} />
              </View>
            ))}
          </View>
        ) : null}
      </VitaSection>

      {twoColumn ? <GrowStrip onUpdate={updateWithOra} /> : null}
    </>
  );

  const rail = (
    <>
      <QuestionsPanel questions={vita.questions} onAsk={(q) => void askQuestion(q)} />
      <UpdatesPanel updates={vita.updates} />
      <SummaryPanel rows={vita.summary} />
    </>
  );

  return (
    <SafeAreaView
      edges={['top']}
      style={[styles.root, { backgroundColor: colors.backgroundPrimary }]}
      testID="contesti-screen"
    >
      <ScrollView
        contentContainerStyle={{
          paddingHorizontal: padH,
          paddingTop: tokens.spacing.lg,
          paddingBottom: ambient.paddingBottom + tokens.spacing.xxl,
          maxWidth: PAGE_MAX_WIDTH,
          width: '100%',
          alignSelf: 'center',
          gap: tokens.spacing.xl,
        }}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={colors.textTertiary}
          />
        }
        showsVerticalScrollIndicator={false}
        testID="vita-scroll"
      >
        {loading && !hasContent ? (
          <VitaSkeleton wide={twoColumn} />
        ) : (
          <>
            <VitaHeader onWhy={() => setWhyOpen(true)} />

            {error && !hasContent ? (
              <ErrorState
                title="Non riesco a caricare Vita"
                message={error}
                onRetry={() => void load()}
              />
            ) : empty ? (
              <VitaEmpty onTalk={updateWithOra} />
            ) : (
              <>
                {partial ? (
                  <Text
                    style={[styles.partial, { color: colors.textTertiary }]}
                    testID="contesti-partial"
                  >
                    Alcune informazioni non sono disponibili al momento.
                  </Text>
                ) : null}

                {/*
                  Content arriving where the skeleton stood: a 200ms fade, no
                  movement, skipped entirely under reduce-motion. The skeleton
                  already holds the real layout, so anything that slid would be
                  describing a displacement that never happened.
                */}
                <Appear>
                  {twoColumn ? (
                    <View style={styles.row}>
                      <View style={styles.mainCol}>{main}</View>
                      <View style={[styles.railCol, { width: RAIL_WIDTH }]}>{rail}</View>
                    </View>
                  ) : (
                    // Phone: the same order, stacked. The rail's panels become
                    // ordinary sections rather than being dropped.
                    <View style={styles.stackAll}>
                      {main}
                      {rail}
                      {/* The invitation closes the page: it is what to do after
                          having read everything, not an interruption in it. */}
                      <GrowStrip onUpdate={updateWithOra} />
                    </View>
                  )}
                </Appear>
              </>
            )}
          </>
        )}
      </ScrollView>

      <WhyItMattersDialog open={whyOpen} onClose={() => setWhyOpen(false)} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  row: { flexDirection: 'row', gap: tokens.spacing.xl, alignItems: 'flex-start' },
  mainCol: { flex: 1, minWidth: 0, gap: tokens.spacing.xxl },
  railCol: { gap: tokens.spacing.lg },
  stackAll: { gap: tokens.spacing.xxl },
  grid3: { flexDirection: 'row', gap: tokens.spacing.md, flexWrap: 'wrap' },
  gridCell: { flexGrow: 1, flexBasis: 260, minWidth: 260, flexShrink: 1 },
  stack: { gap: tokens.spacing.md },
  partial: {
    fontSize: tokens.typography.caption.fontSize,
    lineHeight: tokens.typography.caption.lineHeight,
  },
});
