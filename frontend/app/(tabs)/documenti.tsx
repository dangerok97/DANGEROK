/**
 * Documenti — the documents of a life, understood and usable.
 *
 * Not a file manager. A person opening this page wants to know what they have,
 * which of it ORA has actually read, what needs their attention, what is about
 * to run out, and what they can do with any of it — and the composition is
 * built to answer those in that order rather than to browse a folder.
 *
 * Composition only. One aggregated read supplies the list, the deadlines and
 * the counts, so the sections agree with each other; the upload pipeline,
 * extraction and analysis behind them are untouched. Every affordance on the
 * page maps to something the product genuinely does — a scanner tile and an
 * import-from-connected-apps tile would match the reference exactly and do
 * nothing, and a dead control on the first row is worse than a shorter row.
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
import * as DocumentPicker from 'expo-document-picker';

import { api, type DocumentsLibraryResponse } from '@/src/api/client';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { ErrorState } from '@/src/components/ui/ErrorState';
import { Appear, useAmbientInset } from '@/src/shell';
import { isNetworkError, useOnlineStatus } from '@/src/hooks/use-online-status';
import { humanizeError } from '@/src/utils/errors';
import { haptic } from '@/src/utils/haptic';
import { buildOraConversationHref } from '@/src/ora/oraNav';
import {
  ActionCard,
  CapabilitiesPanel,
  DocumentRow,
  ExpiringPanel,
  LibraryControls,
  LibraryEmpty,
  LibraryHeader,
  LibrarySkeleton,
  NoMatches,
  SummaryPanel,
  WhyDocumentsDialog,
  uploadLabel,
  visibleItems,
  type SortOrder,
  type StatusFilter,
  type UploadPhase,
} from '@/src/components/documents';

const PAGE_MAX_WIDTH = 1320;
const RAIL_WIDTH = 300;
/** Below this the rail has nowhere to sit and the page becomes one column. */
const TWO_COLUMN_MIN = 1100;
/** Below this a document row stacks instead of laying out in columns. */
const ROW_COMPACT_MAX = 720;

/** Pipeline states that mean the work is still in flight. */
const IN_FLIGHT = new Set(['analyzing', 'pending']);

export default function DocumentiScreen() {
  const { colors } = useTheme();
  const ambient = useAmbientInset();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const { markOffline, markOnline } = useOnlineStatus();

  const twoColumn = width >= TWO_COLUMN_MIN;
  const compactRows = width < ROW_COMPACT_MAX;
  const padH = width < 380 ? tokens.spacing.lg : tokens.spacing.xl;

  const [library, setLibrary] = useState<DocumentsLibraryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [whyOpen, setWhyOpen] = useState(false);

  const [query, setQuery] = useState('');
  const [kind, setKind] = useState('all');
  const [status, setStatus] = useState<StatusFilter>('all');
  const [order, setOrder] = useState<SortOrder>('recent');

  const [phase, setPhase] = useState<UploadPhase>('idle');

  const load = useCallback(
    async (opts?: { silent?: boolean }) => {
      if (!opts?.silent) setLoading(true);
      try {
        const res = await api.getDocumentsLibrary();
        markOnline();
        setLibrary(res);
        setError(null);
      } catch (e: any) {
        if (isNetworkError(e)) markOffline();
        setError(humanizeError(e, 'default'));
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
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

  /**
   * Keep watching only while something is genuinely being read.
   *
   * The pipeline is asynchronous, so a document that has just arrived changes
   * state on its own; polling stops the moment nothing is in flight rather
   * than running forever behind an idle page.
   */
  useEffect(() => {
    const busy = (library?.items || []).some((d) => IN_FLIGHT.has(d.status));
    if (!busy) return;
    const t = setInterval(() => void load({ silent: true }), 3000);
    return () => clearInterval(t);
  }, [library, load]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    void load({ silent: true });
  }, [load]);

  /**
   * Upload, through the pipeline that already exists.
   *
   * The two outcomes are kept apart on purpose: a file that was stored but
   * could not be read is still safely in the library, and saying otherwise
   * would make someone think they had lost it.
   */
  const onUpload = useCallback(async () => {
    haptic('tap');
    setError(null);
    try {
      const picked = await DocumentPicker.getDocumentAsync({
        multiple: false,
        copyToCacheDirectory: true,
      });
      if (picked.canceled || !picked.assets?.[0]) return;
      const asset = picked.assets[0];
      setPhase('uploading');
      const up = await api.documentUpload({
        uri: asset.uri,
        name: asset.name || 'documento',
        type: asset.mimeType || 'application/octet-stream',
      });
      haptic(up.duplicate ? 'warning' : 'success');
      setPhase('analyzing');
      await load({ silent: true });
      setPhase('done');
      setTimeout(() => setPhase('idle'), 2500);
      if (up.document?.id) router.push(`/document/${up.document.id}` as any);
    } catch (e: any) {
      haptic('error');
      setPhase('failed');
      setError(humanizeError(e, 'default'));
    }
  }, [load, router]);

  const openDocument = useCallback(
    (id: string) => router.push(`/document/${id}` as any),
    [router],
  );

  /** What ORA can do here, explained by ORA — not by a marketing panel. */
  const askOra = useCallback(
    () => router.push(buildOraConversationHref({ entryPoint: 'document' }) as any),
    [router],
  );

  const resetFilters = useCallback(() => {
    setQuery('');
    setKind('all');
    setStatus('all');
    setOrder('recent');
  }, []);

  const items = library?.items || [];
  const shown = useMemo(
    () => visibleItems(items as any, { query, kind, status, order }),
    [items, query, kind, status, order],
  );
  const empty = !loading && !error && items.length === 0;
  const filtering = query.trim() !== '' || kind !== 'all' || status !== 'all';
  const phaseLabel = uploadLabel(phase);

  const main = (
    <>
      <View style={styles.actions}>
        <ActionCard
          icon="cloud-upload-outline"
          title="Carica documento"
          detail="Aggiungi un documento dal tuo dispositivo"
          cta={phase === 'uploading' ? 'Caricamento…' : 'Carica'}
          onPress={() => void onUpload()}
          busy={phase === 'uploading'}
          testID="documents-upload"
        />
        <ActionCard
          icon="pulse-outline"
          title="Cosa può fare ORA"
          detail="Chiedile come usa i tuoi documenti"
          cta="Scopri"
          onPress={askOra}
          testID="documents-ask-ora"
        />
      </View>

      {phaseLabel && phase !== 'idle' ? (
        <Text
          style={[
            styles.phase,
            { color: phase === 'failed' ? colors.error : colors.textSecondary },
          ]}
          accessibilityLiveRegion="polite"
          testID="documents-phase"
        >
          {phaseLabel}
        </Text>
      ) : null}

      <LibraryControls
        query={query}
        onQuery={setQuery}
        kind={kind}
        kinds={library?.kinds || []}
        onKind={setKind}
        status={status}
        onStatus={setStatus}
        order={order}
        onOrder={setOrder}
      />

      <View
        style={[styles.list, { backgroundColor: colors.surface, borderColor: colors.border }]}
        testID="documents-list"
      >
        {shown.length ? (
          shown.map((it, i) => (
            <DocumentRow
              key={it.id}
              item={it as any}
              first={i === 0}
              compact={compactRows}
              onOpen={() => openDocument(it.id)}
            />
          ))
        ) : (
          <NoMatches onReset={resetFilters} />
        )}
      </View>
    </>
  );

  const rail = (
    <>
      <SummaryPanel rows={library?.summary || []} />
      <ExpiringPanel expiring={library?.expiring || []} onOpen={openDocument} />
      <CapabilitiesPanel />
    </>
  );

  return (
    <SafeAreaView
      edges={['top']}
      style={[styles.root, { backgroundColor: colors.backgroundPrimary }]}
      testID="documenti-screen"
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
        testID="documents-scroll"
      >
        {loading && !library ? (
          <LibrarySkeleton wide={twoColumn} />
        ) : (
          <>
            <LibraryHeader onWhy={() => setWhyOpen(true)} />

            {error && !library ? (
              <ErrorState
                title="Non riesco a caricare i documenti"
                message={error}
                onRetry={() => void load()}
              />
            ) : empty ? (
              <LibraryEmpty onUpload={() => void onUpload()} busy={phase === 'uploading'} />
            ) : (
              <>
                {library?.partial ? (
                  <Text
                    style={[styles.partial, { color: colors.textTertiary }]}
                    testID="documents-partial"
                  >
                    Alcune informazioni non sono disponibili al momento.
                  </Text>
                ) : null}
                {error ? (
                  <Text style={[styles.partial, { color: colors.error }]} testID="documents-error">
                    {error}
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
                    </View>
                  )}
                </Appear>
              </>
            )}
          </>
        )}
      </ScrollView>

      <WhyDocumentsDialog open={whyOpen} onClose={() => setWhyOpen(false)} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  row: { flexDirection: 'row', gap: tokens.spacing.xl, alignItems: 'flex-start' },
  mainCol: { flex: 1, minWidth: 0, gap: tokens.spacing.lg },
  railCol: { gap: tokens.spacing.lg },
  stackAll: { gap: tokens.spacing.lg },
  actions: { flexDirection: 'row', gap: tokens.spacing.md, flexWrap: 'wrap' },
  phase: { fontSize: 13, lineHeight: 19 },
  list: {
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    overflow: 'hidden',
  },
  partial: {
    fontSize: tokens.typography.caption.fontSize,
    lineHeight: tokens.typography.caption.lineHeight,
  },
});
