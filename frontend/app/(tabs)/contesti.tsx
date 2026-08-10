/**
 * Contesti — Life Map V1 (Quiet Premium).
 * Prefers GET /life-map (Prompt 5.1 foundation); falls back to FE compose.
 * Visual IA unchanged — not category navigation, not Home priorities.
 */
import { useCallback, useEffect, useState } from 'react';
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

import { api, LifeProfile, StudyPlan, TravelProject } from '@/src/api/client';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { ErrorState } from '@/src/components/ui/ErrorState';
import { useAmbientInset } from '@/src/shell';
import { isNetworkError, useOnlineStatus } from '@/src/hooks/use-online-status';
import { humanizeError } from '@/src/utils/errors';
import {
  ContextsEmpty,
  ContextsHeader,
  ContextsLoading,
  CurrentPeriodSection,
  LifeAreasSection,
  buildContextsMap,
  mapFromLifeMapApi,
  type ContextsMapModel,
} from '@/src/components/contexts/quiet';

/** Editorial column — coherent with Home (~860), target 760–860. */
const CONTESTI_MAX_WIDTH = 800;

type LoadState = {
  map: ContextsMapModel;
  partial: boolean;
  error: string | null;
};

const EMPTY_MAP: ContextsMapModel = { situations: [], areas: [] };

async function loadFallbackCompose(): Promise<{
  map: ContextsMapModel;
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
  if (profileRes.status === 'fulfilled') {
    profile = profileRes.value.profile ?? null;
  } else {
    failures += 1;
    if (isNetworkError(profileRes.reason)) network = true;
  }
  if (studyRes.status === 'fulfilled') {
    studyPlans = studyRes.value.items || [];
  } else {
    failures += 1;
    if (isNetworkError(studyRes.reason)) network = true;
  }
  if (travelRes.status === 'fulfilled') {
    travelProjects = travelRes.value.items || [];
  } else {
    failures += 1;
    if (isNetworkError(travelRes.reason)) network = true;
  }

  const map = buildContextsMap({ profile, studyPlans, travelProjects });
  const totalFail = failures === 3;
  if (totalFail) {
    const reason =
      profileRes.status === 'rejected'
        ? profileRes.reason
        : studyRes.status === 'rejected'
          ? studyRes.reason
          : travelRes.status === 'rejected'
            ? travelRes.reason
            : null;
    return {
      map: EMPTY_MAP,
      partial: false,
      error: humanizeError(reason, 'default'),
      network,
    };
  }
  return {
    map,
    partial: failures > 0,
    error: null,
    network,
  };
}

export default function ContestiScreen() {
  const { colors } = useTheme();
  const ambient = useAmbientInset();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const padH = width < 360 ? tokens.spacing.lg : tokens.spacing.xl;
  const { markOffline, markOnline } = useOnlineStatus();

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [state, setState] = useState<LoadState>({
    map: EMPTY_MAP,
    partial: false,
    error: null,
  });

  const load = useCallback(async (opts?: { silent?: boolean; force?: boolean }) => {
    if (!opts?.silent) setLoading(true);

    try {
      // Prefer backend Life Map (canonical identity). Fallback only on transport/API failure.
      const lifeMap = await api.getLifeMap({ force: opts?.force === true });
      if (!lifeMap?.ok || !Array.isArray(lifeMap.situations)) {
        throw new Error('life_map_invalid_response');
      }
      markOnline();
      setState({
        map: mapFromLifeMapApi(lifeMap),
        partial: false,
        error: null,
      });
    } catch (e: any) {
      // Resilience only — never overwrite a valid API payload with FE compose.
      if (__DEV__) {
        console.warn(
          '[Contesti] life-map unavailable → FE compose fallback',
          e?.status || e?.message || e,
        );
      }
      if (isNetworkError(e)) markOffline();
      const fallback = await loadFallbackCompose();
      if (fallback.network) markOffline();
      else markOnline();
      setState({
        map: fallback.map,
        partial: fallback.partial,
        error: fallback.error,
      });
    }

    setLoading(false);
    setRefreshing(false);
  }, [markOffline, markOnline]);

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

  const openHref = useCallback(
    (href: string) => {
      if (!href) return;
      router.push(href as any);
    },
    [router],
  );

  const hasContent = state.map.situations.length > 0 || state.map.areas.length > 0;

  return (
    <SafeAreaView
      edges={['top']}
      style={[styles.root, { backgroundColor: colors.backgroundPrimary }]}
      testID="contesti-screen"
    >
      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          {
            paddingBottom: ambient.paddingBottom + tokens.spacing.xxl,
            paddingHorizontal: padH,
          },
        ]}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={colors.textTertiary}
          />
        }
        showsVerticalScrollIndicator={false}
      >
        <View style={[styles.column, { maxWidth: CONTESTI_MAX_WIDTH }]}>
          <ContextsHeader />

          {loading && !hasContent ? (
            <ContextsLoading />
          ) : state.error && !hasContent ? (
            <ErrorState
              title="Non riesco a caricare Contesti"
              message={state.error}
              onRetry={() => void load()}
            />
          ) : !hasContent ? (
            <ContextsEmpty />
          ) : (
            <>
              {state.partial ? (
                <Text
                  style={[styles.partial, { color: colors.textTertiary }]}
                  testID="contesti-partial"
                >
                  Alcune informazioni non sono disponibili al momento.
                </Text>
              ) : null}
              <CurrentPeriodSection
                situations={state.map.situations}
                onOpen={openHref}
              />
              <LifeAreasSection areas={state.map.areas} />
            </>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  scroll: {
    flexGrow: 1,
    paddingTop: tokens.spacing.lg,
  },
  column: {
    width: '100%',
    alignSelf: 'center',
  },
  partial: {
    fontSize: tokens.typography.caption.fontSize,
    lineHeight: tokens.typography.caption.lineHeight,
    marginBottom: tokens.spacing.lg,
  },
});
