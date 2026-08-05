/**
 * ORA Documents V2 — intelligent actions hub (not a file archive).
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View, Text, StyleSheet, FlatList, RefreshControl, Pressable, TextInput,
  ActivityIndicator, ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import Animated, { FadeInDown } from 'react-native-reanimated';
import * as DocumentPicker from 'expo-document-picker';

import { tokens } from '@/src/theme/tokens';
import { api, DocumentHubCard } from '@/src/api/client';
import { haptic } from '@/src/utils/haptic';
import { humanizeError } from '@/src/utils/errors';

type FilterId =
  | 'all'
  | 'events'
  | 'study'
  | 'admin'
  | 'medical'
  | 'review'
  | 'actions'
  | 'done';

const FILTERS: { id: FilterId; label: string }[] = [
  { id: 'all', label: 'Tutti' },
  { id: 'events', label: 'Eventi' },
  { id: 'study', label: 'Studio' },
  { id: 'admin', label: 'Amministrativi' },
  { id: 'medical', label: 'Medici' },
  { id: 'review', label: 'Da verificare' },
  { id: 'actions', label: 'Con azioni' },
  { id: 'done', label: 'Completati' },
];

const MACRO_LABEL: Record<string, string> = {
  event: 'Evento',
  education: 'Studio',
  administrative: 'Amministrativo',
  financial: 'Finanziario',
  medical: 'Medico',
  travel: 'Viaggio',
  receipt: 'Ricevuta',
  contract: 'Contratto',
  generic: 'Generico',
  unknown: 'Da classificare',
};

function formatWhen(iso?: string | null) {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleString('it-IT', {
      day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return null;
  }
}

export default function DocumentiScreen() {
  const router = useRouter();
  const [hub, setHub] = useState<Awaited<ReturnType<typeof api.documentsHub>> | null>(null);
  const [searchItems, setSearchItems] = useState<DocumentHubCard[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<FilterId>('all');
  const [uploading, setUploading] = useState(false);

  const load = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) setLoading(true);
    setError(null);
    try {
      if (query.trim()) {
        const res = await api.documentsSearchIntelligent({ q: query.trim(), limit: 80 });
        setSearchItems(
          (res.items || []).map((d) => ({
            id: d.id,
            display_title: d.display_title || d.user_title || d.filename,
            original_filename: d.original_filename || d.filename,
            macro_category: d.analysis?.macro_category || 'generic',
            short_description: d.analysis?.short_description || d.analysis?.summary,
            pipeline_status: d.pipeline_status,
            pipeline_status_label: d.pipeline_status_label,
            confidence: d.analysis?.confidence,
            utility: d.pipeline_status_label,
            event_start: d.event_candidates?.[0]?.start_datetime,
            event_location: d.event_candidates?.[0]?.venue_name || d.event_candidates?.[0]?.city,
            open_actions: (d.event_candidates || []).filter((e) => e.status === 'proposed').length,
            updated_at: d.updated_at,
            mime_type: d.mime_type,
          })),
        );
        setHub(null);
      } else {
        setSearchItems(null);
        setHub(await api.documentsHub(50));
      }
    } catch (e: any) {
      setError(humanizeError(e));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [query]);

  useEffect(() => { load(); }, [load]);

  // Poll while pipelines are active
  useEffect(() => {
    const active = (hub?.recent || []).some((d) =>
      ['queued', 'extracting', 'understanding', 'classifying', 'analyzing', 'generating_actions'].includes(
        d.pipeline_status || '',
      ),
    );
    if (!active) return;
    const t = setInterval(() => load({ silent: true }), 2500);
    return () => clearInterval(t);
  }, [hub, load]);

  const items = useMemo(() => {
    if (searchItems) return searchItems;
    if (!hub) return [];
    switch (filter) {
      case 'events': return hub.events_found;
      case 'study': return hub.study;
      case 'admin': return hub.administrative;
      case 'medical': return hub.medical;
      case 'review': return hub.needs_review;
      case 'actions': return hub.with_actions;
      case 'done':
        return hub.recent.filter((d) => d.pipeline_status === 'completed');
      default: return hub.recent;
    }
  }, [hub, filter, searchItems]);

  const onUpload = async () => {
    haptic('tap');
    try {
      const res = await DocumentPicker.getDocumentAsync({
        multiple: false, copyToCacheDirectory: true,
      });
      if (res.canceled || !res.assets?.[0]) return;
      const asset = res.assets[0];
      setUploading(true);
      setError(null);
      const up = await api.documentUpload({
        uri: asset.uri,
        name: asset.name || 'documento',
        type: asset.mimeType || 'application/octet-stream',
      });
      haptic(up.duplicate ? 'warning' : 'success');
      await load({ silent: true });
      if (up.duplicate) {
        setError('File già presente — apro la copia esistente.');
      }
      if (up.document?.id) {
        router.push(`/document/${up.document.id}` as any);
      }
    } catch (e: any) {
      haptic('error');
      setError(humanizeError(e));
    } finally {
      setUploading(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']} testID="documenti-screen">
      <View style={styles.header}>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>Documenti</Text>
          <Text style={styles.subtitle}>ORA legge, classifica e propone azioni utili</Text>
        </View>
        <Pressable
          onPress={onUpload}
          disabled={uploading}
          style={({ pressed }) => [styles.uploadBtn, pressed && styles.pressed]}
          accessibilityRole="button"
          accessibilityLabel="Carica documento"
          testID="btn-upload-document"
        >
          {uploading
            ? <ActivityIndicator color={tokens.color.onBrand} />
            : <><Ionicons name="add" size={18} color={tokens.color.onBrand} />
                <Text style={styles.uploadTxt}>Carica</Text></>}
        </Pressable>
      </View>

      {hub?.counts ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.statsRow}>
          <Stat chip="Da verificare" n={hub.counts.needs_review || 0} />
          <Stat chip="Eventi" n={hub.counts.events_found || 0} />
          <Stat chip="Studio" n={hub.counts.study || 0} />
          <Stat chip="Azioni" n={hub.counts.with_actions || 0} />
          <Stat chip="Errori" n={hub.counts.failed || 0} />
        </ScrollView>
      ) : null}

      <View style={styles.searchBox}>
        <Ionicons name="search" size={16} color={tokens.color.onSurfaceMuted} />
        <TextInput
          style={styles.searchInput}
          placeholder="Cerca contenuto, materia, luogo, scadenza…"
          placeholderTextColor={tokens.color.onSurfaceMuted}
          value={query}
          onChangeText={setQuery}
          onSubmitEditing={() => load()}
          returnKeyType="search"
          testID="doc-search-input"
        />
      </View>

      {!query.trim() ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.filters}>
          {FILTERS.map((f) => (
            <Pressable
              key={f.id}
              onPress={() => { haptic('tap'); setFilter(f.id); }}
              style={[styles.filterChip, filter === f.id && styles.filterChipOn]}
            >
              <Text style={[styles.filterTxt, filter === f.id && styles.filterTxtOn]}>{f.label}</Text>
            </Pressable>
          ))}
        </ScrollView>
      ) : null}

      {error ? (
        <Text style={styles.error} testID="doc-error">{error}</Text>
      ) : null}

      {loading && !refreshing ? (
        <View style={styles.center}><ActivityIndicator color={tokens.color.onSurfaceMuted} /></View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(it) => it.id}
          contentContainerStyle={{ padding: 16, paddingBottom: 40, gap: 10 }}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={() => { setRefreshing(true); load({ silent: true }); }}
              tintColor={tokens.color.onSurfaceMuted}
            />
          }
          ListEmptyComponent={
            <View style={styles.empty}>
              <Ionicons name="sparkles-outline" size={36} color={tokens.color.onSurfaceMuted} />
              <Text style={styles.emptyTitle}>Nessun documento qui</Text>
              <Text style={styles.emptyBody}>
                Carica un file: ORA lo interpreta e propone eventi, riassunti o scadenze.
              </Text>
            </View>
          }
          renderItem={({ item, index }) => (
            <Animated.View entering={FadeInDown.delay(Math.min(index, 8) * 40).duration(220)}>
              <DocCard
                item={item}
                onPress={() => {
                  haptic('tap');
                  router.push(`/document/${item.id}` as any);
                }}
              />
            </Animated.View>
          )}
        />
      )}
    </SafeAreaView>
  );
}

function Stat({ chip, n }: { chip: string; n: number }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statN}>{n}</Text>
      <Text style={styles.statL}>{chip}</Text>
    </View>
  );
}

function DocCard({ item, onPress }: { item: DocumentHubCard; onPress: () => void }) {
  const when = formatWhen(item.event_start);
  const cat = MACRO_LABEL[item.macro_category || 'generic'] || item.macro_category;
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [styles.card, pressed && styles.pressed]}
      testID={`doc-card-${item.id}`}
    >
      <View style={styles.cardTop}>
        <Text style={styles.cardTitle} numberOfLines={2}>
          {item.display_title || 'Documento'}
        </Text>
        {typeof item.confidence === 'number' ? (
          <Text style={styles.conf}>{Math.round(item.confidence * 100)}%</Text>
        ) : null}
      </View>
      <Text style={styles.cardFile} numberOfLines={1}>{item.original_filename}</Text>
      <View style={styles.metaRow}>
        <Text style={styles.badge}>{cat}</Text>
        <Text style={styles.status}>{item.pipeline_status_label || item.pipeline_status || '—'}</Text>
      </View>
      {item.short_description ? (
        <Text style={styles.desc} numberOfLines={2}>{item.short_description}</Text>
      ) : null}
      {item.utility ? <Text style={styles.utility}>{item.utility}</Text> : null}
      {(when || item.event_location) ? (
        <Text style={styles.extra} numberOfLines={1}>
          {[when, item.event_location].filter(Boolean).join(' · ')}
        </Text>
      ) : null}
      {(item.open_actions || 0) > 0 ? (
        <Text style={styles.actionHint}>{item.open_actions} azione/i da confermare</Text>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: tokens.color.surface },
  header: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    paddingHorizontal: 16, paddingTop: 8, paddingBottom: 8,
  },
  title: { color: tokens.color.onSurface, fontSize: 28, fontWeight: '700', letterSpacing: -0.5 },
  subtitle: { color: tokens.color.onSurfaceMuted, fontSize: 13, marginTop: 2 },
  uploadBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: tokens.color.brand, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 12,
  },
  uploadTxt: { color: tokens.color.onBrand, fontWeight: '600', fontSize: 14 },
  pressed: { opacity: 0.85 },
  statsRow: { paddingHorizontal: 16, gap: 8, paddingBottom: 8 },
  stat: {
    backgroundColor: tokens.color.surface, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 8,
    minWidth: 72, borderWidth: StyleSheet.hairlineWidth, borderColor: tokens.color.border,
  },
  statN: { color: tokens.color.onSurface, fontWeight: '700', fontSize: 18 },
  statL: { color: tokens.color.onSurfaceMuted, fontSize: 11, marginTop: 2 },
  searchBox: {
    marginHorizontal: 16, marginBottom: 8, flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: tokens.color.surface, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10,
    borderWidth: StyleSheet.hairlineWidth, borderColor: tokens.color.border,
  },
  searchInput: { flex: 1, color: tokens.color.onSurface, fontSize: 15, padding: 0 },
  filters: { paddingHorizontal: 16, gap: 8, paddingBottom: 8 },
  filterChip: {
    paddingHorizontal: 12, paddingVertical: 7, borderRadius: 999,
    backgroundColor: tokens.color.surface, borderWidth: StyleSheet.hairlineWidth, borderColor: tokens.color.border,
  },
  filterChipOn: { backgroundColor: tokens.color.onSurface },
  filterTxt: { color: tokens.color.onSurfaceMuted, fontSize: 13, fontWeight: '500' },
  filterTxtOn: { color: tokens.color.surface },
  error: { color: tokens.color.error, paddingHorizontal: 16, marginBottom: 6, fontSize: 13 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  empty: { alignItems: 'center', paddingTop: 48, gap: 8, paddingHorizontal: 24 },
  emptyTitle: { color: tokens.color.onSurface, fontSize: 17, fontWeight: '600' },
  emptyBody: { color: tokens.color.onSurfaceMuted, fontSize: 14, textAlign: 'center', lineHeight: 20 },
  card: {
    backgroundColor: tokens.color.surfaceSecondary, borderRadius: 16, padding: 14, gap: 4,
    borderWidth: StyleSheet.hairlineWidth, borderColor: tokens.color.border,
  },
  cardTop: { flexDirection: 'row', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start' },
  cardTitle: { flex: 1, color: tokens.color.onSurface, fontSize: 16, fontWeight: '600' },
  conf: { color: tokens.color.onSurfaceMuted, fontSize: 12, fontWeight: '600' },
  cardFile: { color: tokens.color.onSurfaceMuted, fontSize: 12 },
  metaRow: { flexDirection: 'row', gap: 8, alignItems: 'center', marginTop: 4 },
  badge: {
    color: tokens.color.onSurface, fontSize: 11, fontWeight: '600',
    backgroundColor: tokens.color.surfaceSecondary, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8, overflow: 'hidden',
  },
  status: { color: tokens.color.onSurfaceMuted, fontSize: 12 },
  desc: { color: tokens.color.onSurfaceMuted, fontSize: 13, lineHeight: 18, marginTop: 4 },
  utility: { color: tokens.color.brand, fontSize: 13, fontWeight: '500', marginTop: 4 },
  extra: { color: tokens.color.onSurfaceMuted, fontSize: 12, marginTop: 2 },
  actionHint: { color: tokens.color.warning, fontSize: 12, fontWeight: '600', marginTop: 4 },
});
