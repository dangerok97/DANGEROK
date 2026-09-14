/**
 * Chiamate — what ORA did on the phone for you.
 *
 * Not a log. Someone opens this after asking ORA to move an appointment, and
 * the only question they have is whether it got moved. So every layout here
 * answers that in words, and keeps what belongs to the machine — provider
 * ids, model names, tool calls, tokens — out of sight entirely.
 *
 * Two layouts, one page. Wide enough and it is a table, because columns are
 * how you scan twenty calls; on a phone it is stacked rows, because five
 * columns on 375px is five truncations. The breakpoint is not a fallback:
 * below it the table is replaced, not shrunk.
 *
 * The structure comes from the reference mockup — filters, columns, the
 * metadata on show. The drawing does not: hairline rules instead of boxes,
 * one weight of text, and colour only where a state has earned it.
 */
import { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect, useRouter } from 'expo-router';

import { api, type CallCard } from '@/src/api/client';
import { CallFilters, type CallFilter } from '@/src/components/calls/CallFilters';
import { CallRow } from '@/src/components/calls/CallRow';
import { CallsTable } from '@/src/components/calls/CallsTable';
import { ErrorState } from '@/src/components/ui/ErrorState';
import { Appear, useAmbientInset } from '@/src/shell';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { humanizeError } from '@/src/utils/errors';

/** Wide enough for five columns without anything truncating. */
const TABLE_MIN = 860;
const MAX_WIDTH = 1100;

export default function ChiamateScreen() {
  const { colors } = useTheme();
  const ambient = useAmbientInset();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const padH = width < 380 ? tokens.spacing['16'] : tokens.spacing['24'];
  const asTable = width >= TABLE_MIN;

  const [calls, setCalls] = useState<CallCard[] | null>(null);
  const [filter, setFilter] = useState<CallFilter>('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [before, setBefore] = useState('');
  const [loadingMore, setLoadingMore] = useState(false);

  const load = useCallback(
    async (which: CallFilter, opts?: { silent?: boolean }) => {
      if (!opts?.silent) setLoading(true);
      try {
        const res = await api.callHistory({ limit: 20, status: which || undefined });
        setCalls(res.calls ?? []);
        setBefore(res.next_before ?? '');
        setError(null);
      } catch (e) {
        setError(humanizeError(e));
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [],
  );

  useFocusEffect(
    useCallback(() => {
      void load(filter, { silent: true });
    }, [load, filter]),
  );

  const changeFilter = useCallback(
    (next: CallFilter) => {
      setFilter(next);
      setCalls(null);
      void load(next);
    },
    [load],
  );

  /**
   * Older calls, when asked for.
   *
   * No infinite scroll: this list is finite and personal, and a page that
   * keeps growing while you read it decides for you when you are done.
   */
  const loadOlder = useCallback(async () => {
    if (!before || loadingMore) return;
    setLoadingMore(true);
    try {
      const res = await api.callHistory({
        limit: 20,
        before,
        status: filter || undefined,
      });
      setCalls((prima) => [...(prima ?? []), ...(res.calls ?? [])]);
      setBefore(res.next_before ?? '');
    } catch {
      // Una pagina in più che non arriva non deve rovinare quella che c'è.
    } finally {
      setLoadingMore(false);
    }
  }, [before, loadingMore, filter]);

  const open = useCallback(
    (id: string) => router.push(`/chiamate/${id}` as any),
    [router],
  );

  const vuoto = (calls?.length ?? 0) === 0;

  return (
    <SafeAreaView
      edges={['top']}
      style={[styles.safe, { backgroundColor: colors.backgroundPrimary }]}
    >
      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          { paddingHorizontal: padH, paddingBottom: ambient.paddingBottom + 40 },
        ]}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => {
              setRefreshing(true);
              void load(filter, { silent: true });
            }}
            tintColor={colors.textTertiary}
          />
        }
      >
        <View style={[styles.column, { maxWidth: MAX_WIDTH }]}>
          {/*
            La via del ritorno.

            Sul rail Chiamate è una destinazione e si torna cliccando altrove;
            sul telefono non è nella barra — è una sezione che si raggiunge da
            un aggiornamento o da un indirizzo — e senza questa freccia era un
            vicolo cieco. `back()` rispetta da dove sei arrivato; se non c'è un
            «dietro», la Home è il posto giusto dove finire.
          */}
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Torna alla Home"
            testID="chiamate-back"
            onPress={() => {
              if (router.canGoBack()) router.back();
              else router.replace('/(tabs)' as any);
            }}
            hitSlop={12}
            style={({ pressed }) => [pressed && { opacity: 0.7 }]}
          >
            <Text style={[styles.back, { color: colors.textSecondary }]}>
              ← Home
            </Text>
          </Pressable>

          <Appear>
            <Text style={[styles.title, { color: colors.textPrimary }]}>
              Chiamate
            </Text>
            <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
              Le telefonate che ORA ha fatto per te.
            </Text>
          </Appear>

          <CallFilters value={filter} onChange={changeFilter} />

          {loading && calls === null ? (
            <View style={styles.middle}>
              <ActivityIndicator color={colors.textTertiary} />
            </View>
          ) : error ? (
            <ErrorState message={error} onRetry={() => void load(filter)} />
          ) : vuoto ? (
            <Empty filtered={filter !== ''} />
          ) : (
            <>
              {asTable ? (
                <Appear>
                  <CallsTable calls={calls!} onPress={open} />
                </Appear>
              ) : (
                <View style={styles.list}>
                  {calls!.map((call) => (
                    <Appear key={call.id}>
                      <CallRow call={call} onPress={open} />
                    </Appear>
                  ))}
                </View>
              )}

              {before ? (
                <Text
                  accessibilityRole="button"
                  onPress={loadOlder}
                  style={[styles.more, { color: colors.textSecondary }]}
                >
                  {loadingMore ? 'Sto caricando…' : 'Mostra le più vecchie'}
                </Text>
              ) : null}
            </>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

/**
 * Nothing here.
 *
 * Two quiet lines and no illustration: a big empty-state drawing would make a
 * feature that has not happened yet feel like a feature that failed. And a
 * filter that found nothing says so — otherwise it reads as "ORA has never
 * called anyone", which is a different and alarming claim.
 */
function Empty({ filtered }: { filtered: boolean }) {
  const { colors } = useTheme();
  return (
    <View style={styles.empty}>
      <Text style={[styles.emptyTitle, { color: colors.textPrimary }]}>
        {filtered
          ? 'Nessuna chiamata con questo filtro.'
          : 'Le chiamate di ORA appariranno qui.'}
      </Text>
      <Text style={[styles.emptyBody, { color: colors.textSecondary }]}>
        {filtered
          ? 'Prova con «Tutte» per vederle tutte.'
          : 'Quando ORA chiama qualcuno per te, troverai qui esito e dettagli.'}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  scroll: { paddingTop: tokens.spacing['16'], alignItems: 'center' },
  column: { width: '100%', gap: tokens.spacing['20'] },
  back: { fontSize: 15, fontWeight: '500' },
  title: { fontSize: 30, fontWeight: '700', letterSpacing: -0.6 },
  subtitle: { fontSize: 15, marginTop: tokens.spacing['4'], lineHeight: 21 },
  list: { gap: tokens.spacing['12'] },
  middle: { paddingVertical: tokens.spacing['48'], alignItems: 'center' },
  more: {
    textAlign: 'center',
    fontSize: 14,
    fontWeight: '500',
    paddingVertical: tokens.spacing['16'],
  },
  empty: { paddingVertical: tokens.spacing['48'], gap: tokens.spacing['8'] },
  emptyTitle: { fontSize: 17, fontWeight: '600', letterSpacing: -0.2 },
  emptyBody: { fontSize: 15, lineHeight: 22 },
});
