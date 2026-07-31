/**
 * ORA — Iterazione 21
 * Document Insights: dettaglio documento a sezioni (Informazioni /
 * Insights / Contenuto / Metadati / Azioni).
 *
 * Deterministico: nessun LLM, nessun re-OCR. Legge /api/documents/{id}
 * e /api/documents/{id}/insights.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, TextInput,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import Animated, { FadeInDown, FadeIn } from 'react-native-reanimated';
import { tokens } from '@/src/theme/tokens';
import { api, DocumentInsights, DocumentItem } from '@/src/api/client';
import { haptic } from '@/src/utils/haptic';
import { humanizeError } from '@/src/utils/errors';
import { ActionBtn } from '@/src/components/ui/ActionBtn';
import { DocumentActionsBar } from '@/src/components/DocumentActionsBar';
import * as Clipboard from 'expo-clipboard';

type Tab = 'info' | 'insights' | 'content' | 'meta';

const ENTITY_LABELS: Record<string, { label: string; icon: keyof typeof Ionicons.glyphMap }> = {
  persons:        { label: 'Persone',              icon: 'people-outline' },
  organizations:  { label: 'Aziende',              icon: 'business-outline' },
  places:         { label: 'Luoghi',               icon: 'location-outline' },
  dates:          { label: 'Date',                 icon: 'calendar-outline' },
  times:          { label: 'Orari',                icon: 'time-outline' },
  numbers:        { label: 'Numeri',               icon: 'pricetag-outline' },
  amounts:        { label: 'Importi',              icon: 'cash-outline' },
  emails:         { label: 'Email',                icon: 'mail-outline' },
  phones:         { label: 'Telefono',             icon: 'call-outline' },
  urls:           { label: 'Link',                 icon: 'link-outline' },
  iban:           { label: 'IBAN',                 icon: 'card-outline' },
  tax_ids:        { label: 'Codici fiscali',       icon: 'id-card-outline' },
  order_ids:      { label: 'Numeri di ordine',     icon: 'receipt-outline' },
  technical_ids:  { label: 'Identificativi tecnici', icon: 'construct-outline' },
};

function formatBytes(n?: number) {
  if (!n) return '';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1048576).toFixed(1)} MB`;
}
function formatDate(iso?: string | null) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleDateString('it-IT', { day: '2-digit', month: 'short', year: 'numeric' }); }
  catch { return iso; }
}

export default function DocumentDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [doc, setDoc] = useState<DocumentItem | null>(null);
  const [ins, setIns] = useState<DocumentInsights | null>(null);
  const [tab, setTab] = useState<Tab>('info');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const [d, i] = await Promise.all([api.documentGet(String(id)), api.documentInsights(String(id))]);
      setDoc(d);
      setIns(i);
    } catch (e: any) {
      setError(humanizeError(e));
    } finally { setLoading(false); }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const onArchive = async () => {
    if (!doc) return;
    haptic('tap'); setBusy('archive');
    try { await api.documentArchive(doc.id); await load(); } catch (e: any) { setError(humanizeError(e)); }
    setBusy(null);
  };
  const onRestore = async () => {
    if (!doc) return;
    haptic('tap'); setBusy('restore');
    try { await api.documentRestore(doc.id); await load(); } catch (e: any) { setError(humanizeError(e)); }
    setBusy(null);
  };
  const onDelete = async () => {
    if (!doc) return;
    haptic('warning'); setBusy('del');
    try { await api.documentDelete(doc.id); router.back(); } catch (e: any) { setError(humanizeError(e)); }
    setBusy(null);
  };

  if (loading) return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.centerBox}><ActivityIndicator color={tokens.color.onSurfaceMuted} /></View>
    </SafeAreaView>
  );
  if (!doc || !ins) return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.centerBox}>
        <Text style={styles.errorText}>{error || 'Documento non trovato'}</Text>
        <ActionBtn label="Torna indietro" icon="arrow-back" onPress={() => router.back()} />
      </View>
    </SafeAreaView>
  );

  return (
    <SafeAreaView style={styles.safe} edges={['top']} testID="document-detail">
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Pressable onPress={() => { haptic('tap'); router.back(); }} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={22} color={tokens.color.onSurface} />
        </Pressable>
        <View style={{ flex: 1 }}>
          <Text style={styles.title} numberOfLines={1}>{doc.filename}</Text>
          <Text style={styles.subtitle}>{ins.type_label}</Text>
        </View>
      </View>

      <View style={styles.tabs}>
        {(['info', 'insights', 'content', 'meta'] as Tab[]).map(t => (
          <Pressable key={t} onPress={() => setTab(t)} style={[styles.tab, tab === t && styles.tabActive]}>
            <Text style={[styles.tabText, tab === t && styles.tabTextActive]}>
              {t === 'info' ? 'Info' : t === 'insights' ? 'Insights' : t === 'content' ? 'Contenuto' : 'Metadati'}
            </Text>
          </Pressable>
        ))}
      </View>

      {error ? (
        <Animated.View entering={FadeIn} style={styles.errBanner}>
          <Ionicons name="alert-circle" size={14} color={tokens.color.error} />
          <Text style={styles.errorText}>{error}</Text>
        </Animated.View>
      ) : null}

      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: insets.bottom + 100, gap: 12 }}>
        {tab === 'info' && <TabInfo ins={ins} doc={doc} />}
        {tab === 'insights' && <TabInsights ins={ins} />}
        {tab === 'content' && <TabContent ins={ins} query={query} setQuery={setQuery} />}
        {tab === 'meta' && <TabMeta ins={ins} />}
      </ScrollView>

      <View style={[styles.actionsBar, { paddingBottom: insets.bottom + 8 }]}>
        {doc.archived ? (
          <ActionBtn icon="refresh" label="Ripristina" onPress={onRestore} loading={busy === 'restore'} />
        ) : (
          <ActionBtn icon="archive-outline" label="Archivia" onPress={onArchive} loading={busy === 'archive'} />
        )}
        <ActionBtn variant="danger" icon="trash-outline" label="Elimina" onPress={onDelete} loading={busy === 'del'} />
      </View>
    </SafeAreaView>
  );
}

// -----------------------------------------------------------------
function TabInfo({ ins, doc }: { ins: DocumentInsights; doc: DocumentItem }) {
  // Iter22: preferisci resolved_fields (schema-driven, confidence-aware).
  const resolved = (ins.resolved_fields || []).filter(f => f.value && f.value.trim().length > 0);
  const hasResolved = resolved.length > 0;

  return (
    <Animated.View entering={FadeInDown.duration(180)} style={{ gap: 12 }}>
      <Card title={ins.classification?.type_label || ins.type_label || 'Documento'}
            icon="document-text-outline">
        <FieldRow k="Tipo documento" v={ins.type_label} />
        {ins.classification?.confidence != null ? (
          <FieldRow k="Affidabilità" v={`${ins.classification.confidence}/100`} />
        ) : null}
        <FieldRow k="Nome file" v={ins.filename} />
      </Card>

      {hasResolved ? (
        <Card title="Informazioni principali">
          {resolved.map((f, i) => (
            <FieldRow key={`${f.field_key}-${i}`} k={f.label} v={f.value} />
          ))}
        </Card>
      ) : (
        // Fallback Iter21: usa il legacy summary.fields (salta "Tipo" perché
        // già mostrato nell'header sopra).
        <Card title="Riepilogo">
          {ins.summary.fields
            .filter(f => f.label !== 'Tipo')
            .map((f, i) => (
              <FieldRow key={`${f.label}-${i}`} k={f.label} v={f.value} />
            ))}
        </Card>
      )}

      {/* Iter23 — Barra azioni contestuali (solo se ci sono azioni valide). */}
      <DocumentActionsBar insights={ins} />

      <Card title="Storico">
        <FieldRow k="Caricato" v={formatDate(ins.history.created_at)} />
        <FieldRow k="Aggiornato" v={formatDate(ins.history.updated_at)} />
        <FieldRow k="Stato" v={ins.history.archived ? 'Archiviato' : 'Attivo'} />
        <FieldRow k="Versione" v={String(ins.history.version)} />
        {ins.history.upload_source ? <FieldRow k="Sorgente" v={ins.history.upload_source} /> : null}
      </Card>
    </Animated.View>
  );
}

function TabInsights({ ins }: { ins: DocumentInsights }) {
  // Iter22: nascondi dall'elenco entities i valori già risolti come campo
  // semantico (evita duplicazione visiva tra "Info" e "Insights").
  const resolvedValues = useMemo(() => {
    const set = new Set<string>();
    (ins.resolved_fields || []).forEach(f => { if (f.value) set.add(f.value); });
    return set;
  }, [ins.resolved_fields]);

  const techFlat = ins.technical_identifiers?.flat || [];

  const entityKeys = useMemo(
    () => Object.keys(ins.entities)
      .filter(k => k !== 'technical_ids')  // shown as a dedicated section
      .filter(k => (ins.entities[k]?.length || 0) > 0),
    [ins.entities],
  );

  const filteredEntities = useMemo(() => {
    const out: Record<string, string[]> = {};
    for (const k of entityKeys) {
      const vals = (ins.entities[k] || []).filter(v => !resolvedValues.has(v));
      if (vals.length > 0) out[k] = vals;
    }
    return out;
  }, [entityKeys, ins.entities, resolvedValues]);

  const hasAnyEntity = Object.keys(filteredEntities).length > 0;
  const hasTech = techFlat.length > 0;

  return (
    <Animated.View entering={FadeInDown.duration(180)} style={{ gap: 12 }}>
      {hasTech ? (
        <Card title="Identificativi tecnici" icon="construct-outline">
          <View style={styles.chipWrap}>
            {techFlat.map((v, i) => (
              <Pressable
                key={`tech-${i}`}
                onPress={async () => {
                  try {
                    await Clipboard.setStringAsync(v);
                    haptic('success');
                  } catch { haptic('error'); }
                }}
                accessibilityRole="button"
                accessibilityLabel={`Copia identificativo ${v}`}
                testID={`tech-copy-${i}`}
                style={({ pressed }) => [styles.chipEntity, pressed && styles.pressed]}
              >
                <Ionicons name="copy-outline" size={12} color={tokens.color.onSurfaceMuted} style={{ marginRight: 4 }} />
                <Text style={styles.chipEntityText} numberOfLines={1}>{v}</Text>
              </Pressable>
            ))}
          </View>
        </Card>
      ) : null}

      {!hasAnyEntity && !hasTech ? (
        <Card title="Nessuna entità estratta">
          <Text style={styles.metaVal}>
            ORA non ha rilevato entità aggiuntive nel testo del documento.
            Le informazioni principali sono già mostrate nella tab Info.
          </Text>
        </Card>
      ) : null}

      {Object.keys(filteredEntities).map(k => {
        const info = ENTITY_LABELS[k] || { label: humanEntityKey(k), icon: 'ellipse-outline' as const };
        return (
          <Card key={k} title={info.label} icon={info.icon}>
            <View style={styles.chipWrap}>
              {filteredEntities[k].map((v, i) => (
                <View key={`${k}-${i}`} style={styles.chipEntity}>
                  <Text style={styles.chipEntityText} numberOfLines={1}>{v}</Text>
                </View>
              ))}
            </View>
          </Card>
        );
      })}
    </Animated.View>
  );
}

function humanEntityKey(k: string): string {
  // Fallback per chiavi tecniche non mappate: converte "order_ids" → "Order Ids"
  return k
    .replace(/_/g, ' ')
    .replace(/\bids?\b/gi, 'Id')
    .replace(/\b\w/g, c => c.toUpperCase());
}

function TabContent({ ins, query, setQuery }: { ins: DocumentInsights; query: string; setQuery: (v: string) => void }) {
  const highlighted = useMemo(() => renderHighlighted(ins.content.text || '', query), [ins.content.text, query]);
  return (
    <Animated.View entering={FadeInDown.duration(180)} style={{ gap: 12 }}>
      <View style={styles.searchBox}>
        <Ionicons name="search" size={14} color={tokens.color.onSurfaceMuted} />
        <TextInput
          value={query}
          onChangeText={setQuery}
          placeholder="Cerca nel testo…"
          placeholderTextColor={tokens.color.onSurfaceMuted}
          style={styles.searchInput}
        />
        {query ? <Pressable onPress={() => setQuery('')} hitSlop={10}><Ionicons name="close-circle" size={14} color={tokens.color.onSurfaceMuted} /></Pressable> : null}
      </View>
      <Card title={`Contenuto (${ins.content.length} caratteri)`}>
        {ins.content.text ? (
          <Text style={styles.contentText} selectable>{highlighted}</Text>
        ) : (
          <Text style={styles.metaVal}>Nessun testo estratto disponibile.</Text>
        )}
      </Card>
    </Animated.View>
  );
}

function TabMeta({ ins }: { ins: DocumentInsights }) {
  return (
    <Animated.View entering={FadeInDown.duration(180)} style={{ gap: 12 }}>
      <Card title="Estrazione">
        <FieldRow k="Metodo" v={ins.extraction.method} />
        <FieldRow k="Motore" v={ins.extraction.engine || '—'} />
        <FieldRow k="Pagine" v={ins.extraction.pages ? String(ins.extraction.pages) : '—'} />
        <FieldRow k="Lingua" v={ins.extraction.language || '—'} />
        {ins.extraction.confidence != null ? (
          <FieldRow k="Confidence OCR" v={`${Math.round((ins.extraction.confidence || 0) * 100)}%`} />
        ) : null}
        <FieldRow k="Durata" v={ins.extraction.duration_ms != null ? `${Math.round(ins.extraction.duration_ms)} ms` : '—'} />
        {ins.extraction.error_code ? <FieldRow k="Errore" v={ins.extraction.error_code} /> : null}
      </Card>
      <Card title="Metadati tecnici">
        <FieldRow k="Nome file" v={ins.filename} />
        <FieldRow k="Originale" v={ins.technical_metadata.original_filename || '—'} />
        <FieldRow k="Tipo MIME" v={ins.technical_metadata.mime_type || '—'} />
        <FieldRow k="Dimensione" v={formatBytes(ins.technical_metadata.size)} />
        <FieldRow k="Hash" v={(ins.technical_metadata.hash || '').slice(0, 16) + '…'} />
        <FieldRow k="Storage" v={ins.technical_metadata.storage_provider || 'local'} />
      </Card>
    </Animated.View>
  );
}

// -----------------------------------------------------------------
function Card({ title, icon, children }: { title: string; icon?: keyof typeof Ionicons.glyphMap; children: React.ReactNode }) {
  return (
    <View style={styles.card}>
      <View style={styles.cardHead}>
        {icon ? <Ionicons name={icon} size={14} color={tokens.color.onSurfaceMuted} /> : null}
        <Text style={styles.cardTitle}>{title}</Text>
      </View>
      <View style={{ gap: 6 }}>{children}</View>
    </View>
  );
}
function FieldRow({ k, v }: { k: string; v: string }) {
  return (
    <View style={styles.metaLine}>
      <Text style={styles.metaKey}>{k}</Text>
      <Text style={styles.metaVal}>{v}</Text>
    </View>
  );
}

// Text highlight — case-insensitive, safe re-escape
function renderHighlighted(text: string, q: string): React.ReactNode {
  if (!q || q.length < 2) return text;
  const parts: React.ReactNode[] = [];
  const rx = new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
  let last = 0;
  let m: RegExpExecArray | null;
  let count = 0;
  while ((m = rx.exec(text)) !== null && count < 300) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    parts.push(<Text key={`h${count}`} style={styles.highlight}>{m[0]}</Text>);
    last = m.index + m[0].length;
    count++;
    if (m.index === rx.lastIndex) rx.lastIndex++;
  }
  parts.push(text.slice(last));
  return parts;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: tokens.color.surface },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 12, gap: 8 },
  backBtn: { width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center' },
  title: { fontSize: 17, fontWeight: '700', color: tokens.color.onSurface },
  subtitle: { fontSize: 12, color: tokens.color.onSurfaceMuted, marginTop: 2 },
  tabs: { flexDirection: 'row', gap: 6, paddingHorizontal: 12, paddingBottom: 8, flexWrap: 'wrap' },
  tab: { paddingHorizontal: 14, paddingVertical: 6, borderRadius: 16, backgroundColor: tokens.color.surfaceSecondary, borderWidth: 1, borderColor: tokens.color.border },
  tabActive: { backgroundColor: tokens.color.brand, borderColor: tokens.color.brand },
  tabText: { color: tokens.color.onSurface, fontSize: 12, fontWeight: '600' },
  tabTextActive: { color: tokens.color.onBrand },
  centerBox: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12, padding: 24 },
  card: { backgroundColor: tokens.color.surfaceSecondary, borderRadius: tokens.radius.md, padding: 14, borderWidth: 1, borderColor: tokens.color.border, gap: 8 },
  cardHead: { flexDirection: 'row', gap: 6, alignItems: 'center', marginBottom: 2 },
  cardTitle: { color: tokens.color.onSurface, fontSize: 13, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 },
  metaLine: { flexDirection: 'row', gap: 12 },
  metaKey: { color: tokens.color.onSurfaceMuted, fontSize: 12, width: 120 },
  metaVal: { color: tokens.color.onSurface, fontSize: 12, flex: 1 },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  chipEntity: { flexDirection: 'row', alignItems: 'center', backgroundColor: tokens.color.surfaceTertiary, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 12, maxWidth: '100%' },
  chipEntityText: { color: tokens.color.onSurface, fontSize: 12 },
  pressed: { opacity: 0.6 },
  searchBox: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: tokens.color.surfaceSecondary, borderRadius: tokens.radius.md, paddingHorizontal: 10, paddingVertical: 8, borderWidth: 1, borderColor: tokens.color.border },
  searchInput: { flex: 1, color: tokens.color.onSurface, fontSize: 13 },
  contentText: { color: tokens.color.onSurface, fontSize: 12, lineHeight: 18, fontFamily: 'monospace' as any },
  highlight: { backgroundColor: '#fde68a', color: '#111827', fontWeight: '700' },
  errBanner: { flexDirection: 'row', gap: 6, alignItems: 'center', padding: 10, borderRadius: tokens.radius.md, borderWidth: 1, borderColor: tokens.color.error, backgroundColor: tokens.color.errorBg, marginHorizontal: 16, marginBottom: 4 },
  errorText: { color: tokens.color.onSurface, fontSize: 12, flex: 1 },
  actionsBar: { position: 'absolute', left: 0, right: 0, bottom: 0, paddingHorizontal: 16, paddingTop: 10, gap: 8, backgroundColor: tokens.color.surface, borderTopWidth: 1, borderTopColor: tokens.color.border },
});
