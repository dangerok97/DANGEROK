/**
 * ORA — Iterazione 19
 * Tab Documenti: lista, ricerca, filtri, ordinamento, archivio, eliminazione,
 * dettaglio (in-line), upload via expo-document-picker.
 *
 * NON gestisce OCR / AI / estrazione: solo foundation.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, FlatList, RefreshControl, Pressable, TextInput,
  ActivityIndicator, Modal, Platform,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import Animated, { FadeIn, FadeInDown } from 'react-native-reanimated';
import * as DocumentPicker from 'expo-document-picker';

import { tokens } from '@/src/theme/tokens';
import { api, DocumentItem } from '@/src/api/client';
import { haptic } from '@/src/utils/haptic';
import { humanizeError } from '@/src/utils/errors';
import { ActionBtn } from '@/src/components/ui/ActionBtn';

type SortOpt = 'created_desc' | 'created_asc' | 'name_asc' | 'size_desc';

const MIME_ICON: Record<string, keyof typeof Ionicons.glyphMap> = {
  'application/pdf': 'document-text-outline',
  'image/png': 'image-outline',
  'image/jpeg': 'image-outline',
  'image/webp': 'image-outline',
  'text/plain': 'document-outline',
  'text/csv': 'grid-outline',
  'application/zip': 'folder-outline',
};

function iconFor(mime: string) {
  return MIME_ICON[mime] || 'document-attach-outline';
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(iso?: string | null) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleDateString('it-IT', { day: '2-digit', month: 'short', year: 'numeric' });
  } catch { return ''; }
}

export default function DocumentiScreen() {
  const insets = useSafeAreaInsets();
  const [items, setItems] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<SortOpt>('created_desc');
  const [showArchived, setShowArchived] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [selected, setSelected] = useState<DocumentItem | null>(null);

  const load = useCallback(async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) setLoading(true);
    setError(null);
    try {
      const res = await api.documentsList({
        q: query || undefined,
        archived: showArchived ? true : undefined,
        sort,
        limit: 200,
      });
      setItems(res.items);
    } catch (e: any) {
      setError(humanizeError(e));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [query, sort, showArchived]);

  useEffect(() => { load(); }, [load]);

  const onUpload = async () => {
    haptic('tap');
    try {
      const res = await DocumentPicker.getDocumentAsync({
        multiple: false, copyToCacheDirectory: true,
      });
      if (res.canceled || !res.assets?.[0]) return;
      const asset = res.assets[0];
      setUploading(true);
      const up = await api.documentUpload({
        uri: asset.uri,
        name: asset.name || 'documento',
        type: asset.mimeType || 'application/octet-stream',
      });
      haptic(up.duplicate ? 'warning' : 'success');
      await load({ silent: true });
      if (up.duplicate) setError('Questo file era già stato caricato. Ne trovi la copia in elenco.');
    } catch (e: any) {
      haptic('error');
      setError(humanizeError(e));
    } finally {
      setUploading(false);
    }
  };

  const onArchive = async (doc: DocumentItem) => {
    haptic('tap');
    try { await api.documentArchive(doc.id); await load({ silent: true }); }
    catch (e: any) { setError(humanizeError(e)); }
  };
  const onRestore = async (doc: DocumentItem) => {
    haptic('tap');
    try { await api.documentRestore(doc.id); await load({ silent: true }); }
    catch (e: any) { setError(humanizeError(e)); }
  };
  const onDelete = async (doc: DocumentItem) => {
    haptic('warning');
    try { await api.documentDelete(doc.id); await load({ silent: true }); setSelected(null); }
    catch (e: any) { setError(humanizeError(e)); }
  };

  const empty = !loading && items.length === 0;

  return (
    <SafeAreaView style={styles.safe} edges={['top']} testID="documenti-screen">
      <View style={[styles.header, { paddingTop: 4 }]}>
        <Text style={styles.title}>Documenti</Text>
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
            : <><Ionicons name="cloud-upload-outline" size={16} color={tokens.color.onBrand} />
                <Text style={styles.uploadTxt}>Carica</Text></>}
        </Pressable>
      </View>

      <View style={styles.searchRow}>
        <View style={styles.searchBox}>
          <Ionicons name="search" size={16} color={tokens.color.onSurfaceMuted} />
          <TextInput
            style={styles.searchInput}
            placeholder="Cerca per nome, tag, tipo…"
            placeholderTextColor={tokens.color.onSurfaceMuted}
            value={query}
            onChangeText={setQuery}
            onSubmitEditing={() => load()}
            returnKeyType="search"
            testID="doc-search-input"
          />
          {query ? (
            <Pressable onPress={() => { setQuery(''); }} hitSlop={10}>
              <Ionicons name="close-circle" size={16} color={tokens.color.onSurfaceMuted} />
            </Pressable>
          ) : null}
        </View>
      </View>

      <View style={styles.chipsRow}>
        <FilterChip label="Recenti" active={sort === 'created_desc'} onPress={() => setSort('created_desc')} />
        <FilterChip label="A-Z"     active={sort === 'name_asc'}     onPress={() => setSort('name_asc')} />
        <FilterChip label="Peso"    active={sort === 'size_desc'}    onPress={() => setSort('size_desc')} />
        <View style={{ width: 8 }} />
        <FilterChip
          label={showArchived ? 'Archivio' : 'Attivi'}
          icon={showArchived ? 'archive' : 'file-tray-full-outline'}
          active
          onPress={() => setShowArchived(v => !v)}
        />
      </View>

      {error ? (
        <Animated.View entering={FadeIn.duration(160)} style={styles.errorBanner}>
          <Ionicons name="alert-circle" size={14} color={tokens.color.error} />
          <Text style={styles.errorText} numberOfLines={2}>{error}</Text>
        </Animated.View>
      ) : null}

      {loading ? (
        <View style={styles.centerBox}><ActivityIndicator color={tokens.color.onSurfaceMuted} /></View>
      ) : empty ? (
        <EmptyState onUpload={onUpload} archived={showArchived} />
      ) : (
        <FlatList
          data={items}
          keyExtractor={(x) => x.id}
          contentContainerStyle={{ paddingBottom: insets.bottom + 96, paddingHorizontal: 16, gap: 8 }}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load({ silent: true }); }} tintColor={tokens.color.onSurfaceMuted} />
          }
          renderItem={({ item }) => (
            <DocRow item={item} onOpen={() => setSelected(item)} />
          )}
        />
      )}

      <Modal
        visible={!!selected}
        animationType="slide"
        transparent
        onRequestClose={() => setSelected(null)}
      >
        {selected ? (
          <DetailSheet
            doc={selected}
            onClose={() => setSelected(null)}
            onArchive={() => onArchive(selected)}
            onRestore={() => onRestore(selected)}
            onDelete={() => onDelete(selected)}
          />
        ) : null}
      </Modal>
    </SafeAreaView>
  );
}

function FilterChip({ label, active, onPress, icon }: { label: string; active: boolean; onPress: () => void; icon?: keyof typeof Ionicons.glyphMap }) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.chip, active && styles.chipActive, pressed && styles.pressed]}>
      {icon ? <Ionicons name={icon} size={12} color={active ? tokens.color.onBrand : tokens.color.onSurface} /> : null}
      <Text style={[styles.chipText, active && styles.chipTextActive]}>{label}</Text>
    </Pressable>
  );
}

function DocRow({ item, onOpen }: { item: DocumentItem; onOpen: () => void }) {
  return (
    <Pressable
      onPress={onOpen}
      style={({ pressed }) => [styles.row, pressed && styles.pressed]}
      testID={`doc-row-${item.id}`}
    >
      <View style={styles.iconWrap}>
        <Ionicons name={iconFor(item.mime_type)} size={20} color={tokens.color.onSurface} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.rowTitle} numberOfLines={1}>{item.filename}</Text>
        <Text style={styles.rowMeta}>{formatDate(item.created_at)} · {formatSize(item.size)}</Text>
        {item.tags?.length ? (
          <View style={styles.tagsRow}>
            {item.tags.slice(0, 3).map(t => (
              <View key={t} style={styles.tag}><Text style={styles.tagText}>{t}</Text></View>
            ))}
          </View>
        ) : null}
      </View>
      {item.archived ? <Ionicons name="archive" size={16} color={tokens.color.onSurfaceMuted} /> : null}
    </Pressable>
  );
}

function EmptyState({ onUpload, archived }: { onUpload: () => void; archived: boolean }) {
  return (
    <Animated.View entering={FadeInDown.duration(200)} style={styles.centerBox}>
      <Ionicons name={archived ? 'archive-outline' : 'document-outline'} size={40} color={tokens.color.onSurfaceMuted} />
      <Text style={styles.emptyTitle}>
        {archived ? 'Nessun documento archiviato' : 'Nessun documento ancora'}
      </Text>
      <Text style={styles.emptyBody}>
        {archived
          ? 'Quando archivi un documento lo trovi qui.'
          : 'Carica il tuo primo file per iniziare. Contratti, ricevute, scontrini, foto — tutto al sicuro.'}
      </Text>
      {!archived ? (
        <View style={{ marginTop: 16, width: 240 }}>
          <ActionBtn primary icon="cloud-upload-outline" label="Carica un documento" onPress={onUpload} />
        </View>
      ) : null}
    </Animated.View>
  );
}

function DetailSheet({ doc, onClose, onArchive, onRestore, onDelete }: {
  doc: DocumentItem; onClose: () => void; onArchive: () => void; onRestore: () => void; onDelete: () => void;
}) {
  return (
    <View style={styles.sheetOverlay}>
      <Pressable style={StyleSheet.absoluteFill} onPress={onClose} />
      <Animated.View entering={FadeInDown.duration(220)} style={styles.sheet}>
        <View style={styles.sheetHead}>
          <View style={styles.iconWrap}>
            <Ionicons name={iconFor(doc.mime_type)} size={22} color={tokens.color.onSurface} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.sheetTitle} numberOfLines={2}>{doc.filename}</Text>
            <Text style={styles.rowMeta}>{doc.mime_type} · {formatSize(doc.size)}</Text>
          </View>
          <Pressable onPress={onClose} hitSlop={12} accessibilityLabel="Chiudi">
            <Ionicons name="close" size={20} color={tokens.color.onSurfaceMuted} />
          </Pressable>
        </View>

        <View style={styles.metaBlock}>
          <MetaLine k="Caricato" v={formatDate(doc.created_at)} />
          <MetaLine k="Aggiornato" v={formatDate(doc.updated_at)} />
          <MetaLine k="Hash" v={doc.hash.slice(0, 10) + '…'} />
          {doc.tags?.length ? <MetaLine k="Tag" v={doc.tags.join(', ')} /> : null}
          {doc.notes ? <MetaLine k="Note" v={doc.notes} /> : null}
          <MetaLine k="Stato" v={doc.archived ? 'Archiviato' : 'Attivo'} />
        </View>

        <View style={{ gap: 8, marginTop: 12 }}>
          {doc.archived ? (
            <ActionBtn icon="refresh" label="Ripristina" onPress={onRestore} />
          ) : (
            <ActionBtn icon="archive-outline" label="Archivia" onPress={onArchive} />
          )}
          <ActionBtn variant="danger" icon="trash-outline" label="Elimina" onPress={onDelete} testID="btn-delete-doc" />
        </View>
      </Animated.View>
    </View>
  );
}

function MetaLine({ k, v }: { k: string; v: string }) {
  return (
    <View style={styles.metaLine}>
      <Text style={styles.metaKey}>{k}</Text>
      <Text style={styles.metaVal} numberOfLines={3}>{v}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: tokens.color.surface },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingBottom: 8 },
  title: { fontSize: 22, fontWeight: '800', color: tokens.color.onSurface },
  uploadBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: tokens.color.brand, borderRadius: 20,
    paddingHorizontal: 12, paddingVertical: 8, minWidth: 80, justifyContent: 'center',
  },
  uploadTxt: { color: tokens.color.onBrand, fontWeight: '700', fontSize: 13 },
  searchRow: { paddingHorizontal: 16, paddingBottom: 8 },
  searchBox: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: tokens.radius.md,
    paddingHorizontal: 12, paddingVertical: Platform.OS === 'ios' ? 10 : 4,
    borderWidth: 1, borderColor: tokens.color.border,
  },
  searchInput: { flex: 1, color: tokens.color.onSurface, fontSize: 14, paddingVertical: 4 },
  chipsRow: { flexDirection: 'row', gap: 8, paddingHorizontal: 16, paddingBottom: 10, flexWrap: 'wrap' },
  chip: {
    flexDirection: 'row', gap: 4, alignItems: 'center',
    paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16,
    backgroundColor: tokens.color.surfaceSecondary,
    borderWidth: 1, borderColor: tokens.color.border,
  },
  chipActive: { backgroundColor: tokens.color.brand, borderColor: tokens.color.brand },
  chipText: { color: tokens.color.onSurface, fontSize: 12, fontWeight: '600' },
  chipTextActive: { color: tokens.color.onBrand },
  errorBanner: {
    marginHorizontal: 16, marginBottom: 8, padding: 10, borderRadius: tokens.radius.md,
    borderWidth: 1, borderColor: tokens.color.error, backgroundColor: tokens.color.errorBg,
    flexDirection: 'row', gap: 8, alignItems: 'center',
  },
  errorText: { color: tokens.color.onSurface, fontSize: 12, flex: 1 },
  centerBox: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 24, gap: 6 },
  emptyTitle: { color: tokens.color.onSurface, fontWeight: '700', fontSize: 16, marginTop: 12 },
  emptyBody: { color: tokens.color.onSurfaceMuted, fontSize: 13, textAlign: 'center', lineHeight: 18 },
  row: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    padding: 12, borderRadius: tokens.radius.md,
    backgroundColor: tokens.color.surfaceSecondary,
    borderWidth: 1, borderColor: tokens.color.border,
    minHeight: 60,
  },
  iconWrap: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: tokens.color.surfaceTertiary,
    alignItems: 'center', justifyContent: 'center',
  },
  rowTitle: { color: tokens.color.onSurface, fontSize: 14, fontWeight: '600' },
  rowMeta: { color: tokens.color.onSurfaceMuted, fontSize: 11, marginTop: 2 },
  tagsRow: { flexDirection: 'row', gap: 6, marginTop: 6, flexWrap: 'wrap' },
  tag: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10, backgroundColor: tokens.color.surfaceTertiary },
  tagText: { color: tokens.color.onSurfaceMuted, fontSize: 10, fontWeight: '600' },
  sheetOverlay: { flex: 1, backgroundColor: tokens.color.scrim, justifyContent: 'flex-end' },
  sheet: {
    backgroundColor: tokens.color.surface,
    borderTopLeftRadius: 20, borderTopRightRadius: 20,
    padding: 20, paddingBottom: 32,
    borderTopWidth: 1, borderTopColor: tokens.color.border,
    gap: 8,
  },
  sheetHead: { flexDirection: 'row', gap: 12, alignItems: 'center' },
  sheetTitle: { color: tokens.color.onSurface, fontSize: 16, fontWeight: '700' },
  metaBlock: { marginTop: 12, gap: 6 },
  metaLine: { flexDirection: 'row', gap: 8 },
  metaKey: { color: tokens.color.onSurfaceMuted, fontSize: 12, width: 90 },
  metaVal: { color: tokens.color.onSurface, fontSize: 12, flex: 1 },
  pressed: { opacity: 0.7 },
});
