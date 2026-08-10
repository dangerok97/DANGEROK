/**
 * Memoria — Life Memory V1 (Quiet Premium).
 * Prefers GET /life-memory. No FE compose of raw profile/notes into "memory".
 * Visual: inspectable durable knowledge — not ask-search, not Contesti clone.
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

import { api } from '@/src/api/client';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { ErrorState } from '@/src/components/ui/ErrorState';
import { useAmbientInset } from '@/src/shell';
import { isNetworkError, useOnlineStatus } from '@/src/hooks/use-online-status';
import { humanizeError } from '@/src/utils/errors';
import { ConversationEngine } from '@/src/conversation-engine';
import {
  MemoryEmpty,
  MemoryGroupSection,
  MemoryHeader,
  MemoryLoading,
  mapFromMemoryApi,
  type MemoryMapModel,
  type MemoryRowModel,
} from '@/src/components/memory/quiet';

const MEMORIA_MAX_WIDTH = 800;

const EMPTY_MAP: MemoryMapModel = { groups: [], partial: false };

export default function MemoriaScreen() {
  const { colors } = useTheme();
  const ambient = useAmbientInset();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const padH = width < 360 ? tokens.spacing.lg : tokens.spacing.xl;
  const { markOffline, markOnline } = useOnlineStatus();

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [map, setMap] = useState<MemoryMapModel>(EMPTY_MAP);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (opts?: { silent?: boolean; force?: boolean }) => {
    if (!opts?.silent) setLoading(true);

    try {
      const lifeMemory = await api.getLifeMemory({ force: opts?.force === true });
      if (!lifeMemory?.ok || !Array.isArray(lifeMemory.memories)) {
        throw new Error('life_memory_invalid_response');
      }
      markOnline();
      setMap(mapFromMemoryApi(lifeMemory));
      setError(null);
    } catch (e: any) {
      if (__DEV__) {
        console.warn(
          '[Memoria] life-memory unavailable — honest empty/error (no FE invent)',
          e?.status || e?.message || e,
        );
      }
      if (isNetworkError(e)) markOffline();
      else markOnline();
      setMap(EMPTY_MAP);
      setError(humanizeError(e, 'default'));
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

  const onClarify = useCallback(
    async (item: MemoryRowModel) => {
      try {
        await ConversationEngine.start(item.beliefStatement || item.statement, router, {
          origin: 'memoria',
          context: {
            memory_id: item.id,
            memory_clarification: { memory_id: item.id },
          },
        });
      } catch {
        // Fallback: direct clarify API if CE bridge fails
        try {
          const res = await api.lifeMemoryClarifyStart(item.id);
          if (res?.route) router.push(res.route as any);
          else if (res?.session?.id) router.push(`/memory-clarify/${res.session.id}` as any);
        } catch (e2: any) {
          setError(humanizeError(e2, 'default'));
        }
      }
    },
    [router],
  );

  const hasContent = map.groups.some((g) => g.items.length > 0);

  return (
    <SafeAreaView
      edges={['top']}
      style={[styles.root, { backgroundColor: colors.backgroundPrimary }]}
      testID="memoria-screen"
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
        <View style={[styles.column, { maxWidth: MEMORIA_MAX_WIDTH }]}>
          <MemoryHeader />

          {loading && !hasContent ? (
            <MemoryLoading />
          ) : error && !hasContent ? (
            <ErrorState
              title="Non riesco a caricare Memoria"
              message={error}
              onRetry={() => void load()}
            />
          ) : !hasContent ? (
            <MemoryEmpty onTellOra={() => router.push('/(tabs)/ora' as any)} />
          ) : (
            <>
              {map.partial ? (
                <Text
                  style={[styles.partial, { color: colors.textTertiary }]}
                  testID="memory-partial"
                >
                  Alcune fonti non sono disponibili al momento.
                </Text>
              ) : null}
              {map.groups.map((g) => (
                <MemoryGroupSection key={g.id} group={g} onClarify={onClarify} />
              ))}
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
