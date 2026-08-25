/**
 * ORA Documents V2 — dynamic detail by document utility.
 * Primary surface: intelligent analysis, events, study, actions.
 * Original file always available under Contenuto / Metadati.
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
import {
  api,
  DocumentAnalysisResponse,
  DocumentInsights,
  DocumentItem,
  EventCandidate,
} from '@/src/api/client';
import { haptic } from '@/src/utils/haptic';
import { humanizeError } from '@/src/utils/errors';
import { ActionBtn } from '@/src/components/ui/ActionBtn';
import { DocumentActionsBar } from '@/src/components/DocumentActionsBar';
import { DocumentUtilityPanel } from '@/src/components/documents/DocumentUtilityPanel';
import { buildOraConversationHref } from '@/src/ora/oraNav';
import { categoryLabel } from '@/src/components/documents/libraryView';
import * as Clipboard from 'expo-clipboard';

type Tab = 'info' | 'insights' | 'content' | 'meta';

/** Editorial width — the same reading column the other PX1.x surfaces use. */
const DETAIL_MAX_WIDTH = 960;

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
  const [analysis, setAnalysis] = useState<DocumentAnalysisResponse | null>(null);
  const [tab, setTab] = useState<Tab>('info');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [askQ, setAskQ] = useState('');
  const [askA, setAskA] = useState<string | null>(null);
  const [flashOpen, setFlashOpen] = useState<Record<string, boolean>>({});
  const [quizAnswer, setQuizAnswer] = useState('');

  const load = useCallback(async (opts?: { silent?: boolean }) => {
    if (!id) return;
    if (!opts?.silent) setLoading(true);
    setError(null);
    try {
      const [d, i, a] = await Promise.all([
        api.documentGet(String(id)),
        api.documentInsights(String(id)),
        api.documentAnalysis(String(id)).catch(() => null),
      ]);
      setDoc(d);
      setIns(i);
      setAnalysis(a);
    } catch (e: any) {
      setError(humanizeError(e));
    } finally { setLoading(false); }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  // Poll while pipeline is running
  useEffect(() => {
    const st = analysis?.pipeline_status;
    if (!st || ['completed', 'failed', 'needs_review', 'action_required', 'awaiting_confirmation'].includes(st)) return;
    if (analysis?.analysis && st === 'action_required') return;
    const t = setInterval(() => { load({ silent: true }); }, 1500);
    return () => clearInterval(t);
  }, [analysis?.pipeline_status, analysis?.analysis, load]);

  /** Shared by the error card and the secondary actions — one behaviour, two places. */
  const onReanalyze = async () => {
    if (!doc) return;
    haptic('tap'); setBusy('reanalyze');
    try { await api.documentReanalyze(doc.id); await load({ silent: true }); }
    catch (e: any) { setError(humanizeError(e)); }
    setBusy(null);
  };
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
      <View style={styles.column}>
        <View style={styles.header}>
          <Pressable
            onPress={() => {
              haptic('tap');
              if (router.canGoBack()) router.back();
              else router.replace('/(tabs)/documenti' as any);
            }}
            hitSlop={12}
            style={styles.backBtn}
            accessibilityRole="button"
            accessibilityLabel="Indietro"
          >
            <Ionicons name="chevron-back" size={22} color={tokens.color.onSurfaceMuted} />
          </Pressable>
          <View style={{ flex: 1 }}>
            <Text style={styles.title} numberOfLines={2} accessibilityRole="header" aria-level={1}>
              {analysis?.display_title || analysis?.analysis?.suggested_title || doc.display_title || doc.filename}
            </Text>
            <Text style={styles.subtitle}>
              {analysis?.pipeline_status_label || ins.type_label}
              {categoryLabel(analysis?.analysis?.macro_category) ? ` · ${categoryLabel(analysis?.analysis?.macro_category)}` : ''}
            </Text>
          </View>
        </View>
      </View>

      {/*
        The way out of reading and into asking.

        The document travels with the route as an opaque id and is bound to the
        conversation as context on the first turn, so someone can arrive here,
        tap this and write "cosa devo controllare?" without attaching the file
        again or explaining what it is. Placed above the tabs because it is the
        one action that is useful whichever tab you were about to open.
      */}
      <View style={styles.column}>
        <Pressable
          onPress={() => {
            haptic('tap');
            router.push(
              buildOraConversationHref({ documentId: doc.id, entryPoint: 'document' }) as any,
            );
          }}
          style={({ pressed }) => [styles.askOra, pressed && { opacity: 0.75 }]}
          accessibilityRole="button"
          testID="document-ask-ora"
        >
          <Ionicons name="chatbubble-ellipses-outline" size={16} color={tokens.color.onBrand} />
          <Text style={styles.askOraLabel}>Chiedi a ORA su questo documento</Text>
        </Pressable>

        {/*
          Tabs as a quiet row of labels with a rule under the active one. The
          filled pills read as four competing buttons, which put navigation on
          the same footing as the one action the page is actually for.
        */}
        <View style={styles.tabs}>
          {(['info', 'insights', 'content', 'meta'] as Tab[]).map(t => (
            <Pressable
              key={t}
              onPress={() => setTab(t)}
              style={[styles.tab, tab === t && styles.tabActive]}
              accessibilityRole="tab"
              accessibilityState={{ selected: tab === t }}
              aria-selected={tab === t}
            >
              <Text style={[styles.tabText, tab === t && styles.tabTextActive]}>
                {t === 'info' ? 'Utilità' : t === 'insights' ? 'Dettagli' : t === 'content' ? 'Originale' : 'File'}
              </Text>
            </Pressable>
          ))}
        </View>
      </View>

      {error ? (
        <Animated.View entering={FadeIn} style={styles.errBanner}>
          <Ionicons name="alert-circle" size={14} color={tokens.color.error} />
          <Text style={styles.errorText}>{error}</Text>
        </Animated.View>
      ) : null}

      <ScrollView
        contentContainerStyle={{
          paddingHorizontal: tokens.spacing.lg,
          paddingTop: tokens.spacing.lg,
          // The action bar is gone from the bottom of the screen, so the page
          // only needs room to breathe past the safe area.
          paddingBottom: insets.bottom + tokens.spacing.xxxl,
          gap: tokens.spacing.md,
          width: '100%',
          maxWidth: DETAIL_MAX_WIDTH,
          alignSelf: 'center',
        }}
        showsVerticalScrollIndicator={false}
      >
        {tab === 'info' && (
          <TabInfo
            ins={ins}
            doc={doc}
            analysis={analysis}
            busy={busy}
            flashOpen={flashOpen}
            setFlashOpen={setFlashOpen}
            quizAnswer={quizAnswer}
            setQuizAnswer={setQuizAnswer}
            onConfirmEvent={async (ev, syncToGoogle) => {
              setBusy(`ev-${ev.id}${syncToGoogle ? '-g' : ''}`);
              try {
                const res = await api.documentConfirmEvent(doc.id, ev.id, {
                  sync_to_google: !!syncToGoogle,
                });
                haptic('success');
                if (syncToGoogle && res.google_sync && (res.google_sync as any).ok === false) {
                  setError(
                    String(
                      (res.google_sync as any).error ||
                        'Salvato in ORA; sincronizzazione Google non riuscita.',
                    ),
                  );
                }
                await load({ silent: true });
              } catch (e: any) {
                setError(humanizeError(e));
              } finally { setBusy(null); }
            }}
            onDismissEvent={async (ev) => {
              setBusy(`ev-${ev.id}`);
              try {
                await api.documentDismissEvent(doc.id, ev.id);
                await load({ silent: true });
              } catch (e: any) {
                setError(humanizeError(e));
              } finally { setBusy(null); }
            }}
            onRemindEvent={async (ev) => {
              setBusy(`ev-${ev.id}`);
              try {
                await api.documentRemindEvent(doc.id, ev.id);
                await load({ silent: true });
              } catch (e: any) {
                setError(humanizeError(e));
              } finally { setBusy(null); }
            }}
            onReanalyze={onReanalyze}
            onStudy={async (action) => {
              setBusy(`study-${action}`);
              try {
                await api.documentStudy(doc.id, action);
                haptic('success');
                await load({ silent: true });
              } catch (e: any) {
                setError(humanizeError(e));
              } finally { setBusy(null); }
            }}
            onQuizAnswer={async () => {
              setBusy('quiz');
              try {
                await api.documentQuizAnswer(doc.id, quizAnswer);
                setQuizAnswer('');
                haptic('success');
                await load({ silent: true });
              } catch (e: any) {
                setError(humanizeError(e));
              } finally { setBusy(null); }
            }}
            onAdminComplete={async (index) => {
              setBusy(`admin-${index}`);
              try {
                await api.documentAdminComplete(doc.id, index, true);
                haptic('success');
                await load({ silent: true });
              } catch (e: any) {
                setError(humanizeError(e));
              } finally { setBusy(null); }
            }}
            onAdminDeadline={async (syncGoogle) => {
              setBusy('deadline');
              try {
                await api.documentAdminDeadline(doc.id, syncGoogle);
                haptic('success');
                await load({ silent: true });
              } catch (e: any) {
                setError(humanizeError(e));
              } finally { setBusy(null); }
            }}
            onPatchFields={async (body) => {
              setBusy('patch');
              try {
                await api.documentPatchAnalysis(doc.id, body);
                haptic('success');
                await load({ silent: true });
              } catch (e: any) {
                setError(humanizeError(e));
              } finally { setBusy(null); }
            }}
            askQ={askQ}
            setAskQ={setAskQ}
            askA={askA}
            onAsk={async () => {
              if (!askQ.trim()) return;
              setBusy('ask');
              try {
                const r = await api.documentAsk(doc.id, askQ.trim());
                setAskA(`[${r.grounding}] ${r.answer}`);
              } catch (e: any) {
                setError(humanizeError(e));
              } finally { setBusy(null); }
            }}
          />
        )}
        {tab === 'insights' && <TabInsights ins={ins} />}
        {tab === 'content' && <TabContent ins={ins} query={query} setQuery={setQuery} />}
        {tab === 'meta' && <TabMeta ins={ins} />}

        {/*
          Archiving and deleting close the page rather than sitting in a bar
          pinned across the bottom of it. They are things you do when you have
          finished reading, and a permanent strip gave two rarely-wanted
          actions — one of them destructive — the most persistent position on
          the screen.
        */}
        <View style={styles.secondary}>
          <View style={styles.secondaryRow}>
            <ActionBtn
              icon="refresh"
              label="Riesegui analisi"
              onPress={onReanalyze}
              loading={busy === 'reanalyze'}
            />
            {doc.archived ? (
              <ActionBtn icon="refresh" label="Ripristina" onPress={onRestore} loading={busy === 'restore'} />
            ) : (
              <ActionBtn icon="archive-outline" label="Archivia" onPress={onArchive} loading={busy === 'archive'} />
            )}
            <ActionBtn variant="danger" icon="trash-outline" label="Elimina" onPress={onDelete} loading={busy === 'del'} />
          </View>
        </View>
      </ScrollView>


    </SafeAreaView>
  );
}

// -----------------------------------------------------------------
function TabInfo({
  ins, doc, analysis, busy, onConfirmEvent, onDismissEvent, onRemindEvent, onReanalyze,
  onStudy, onQuizAnswer, onAdminComplete, onAdminDeadline, onPatchFields,
  askQ, setAskQ, askA, onAsk, flashOpen, setFlashOpen, quizAnswer, setQuizAnswer,
}: {
  ins: DocumentInsights;
  doc: DocumentItem;
  analysis: DocumentAnalysisResponse | null;
  busy: string | null;
  onConfirmEvent: (ev: EventCandidate, syncToGoogle?: boolean) => void;
  onDismissEvent: (ev: EventCandidate) => void;
  onRemindEvent: (ev: EventCandidate) => void;
  onReanalyze: () => void;
  onStudy: (action: string) => void;
  onQuizAnswer: () => void;
  onAdminComplete: (index: number) => void;
  onAdminDeadline: (syncGoogle: boolean) => void;
  onPatchFields: (body: {
    user_title?: string;
    admin_analysis?: Record<string, unknown>;
  }) => void;
  askQ: string;
  setAskQ: (v: string) => void;
  askA: string | null;
  onAsk: () => void;
  flashOpen: Record<string, boolean>;
  setFlashOpen: React.Dispatch<React.SetStateAction<Record<string, boolean>>>;
  quizAnswer: string;
  setQuizAnswer: (v: string) => void;
}) {
  return (
    <Animated.View entering={FadeInDown.duration(180)} style={{ gap: 12 }}>
      <DocumentUtilityPanel
        doc={doc}
        ins={ins}
        analysis={analysis}
        h={{
          busy,
          onConfirmEvent,
          onDismissEvent,
          onRemindEvent,
          onReanalyze,
          onStudy,
          onQuizAnswer,
          onAdminComplete,
          onAdminDeadline,
          onPatchFields,
          askQ,
          setAskQ,
          askA,
          onAsk,
          quizAnswer,
          setQuizAnswer,
          flashOpen,
          setFlashOpen,
        }}
      />
      <DocumentActionsBar insights={ins} />
      {/*
        Origin, in the terms someone would describe it: when it arrived and
        whether it is still in the library. The internal revision number and
        the upload channel are plumbing — neither tells a person anything they
        could use or check.
      */}
      <Card title="Origine">
        <FieldRow k="Caricato" v={formatDate(ins.history.created_at)} />
        <FieldRow k="Aggiornato" v={formatDate(ins.history.updated_at)} />
        <FieldRow k="Stato" v={ins.history.archived ? 'Archiviato' : 'Attivo'} />
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
  safe: { flex: 1, backgroundColor: tokens.color.backgroundPrimary },
  /** A reading column, not a full-bleed page. */
  column: { width: '100%', maxWidth: DETAIL_MAX_WIDTH, alignSelf: 'center' },
  header: {
    flexDirection: 'row', alignItems: 'flex-start', gap: 4,
    paddingHorizontal: tokens.spacing.lg, paddingTop: tokens.spacing.sm,
    paddingBottom: tokens.spacing.md,
  },
  backBtn: {
    width: tokens.touch.min, height: tokens.touch.min,
    alignItems: 'center', justifyContent: 'center', marginLeft: -12,
  },
  title: { fontSize: 24, fontWeight: '700', letterSpacing: -0.5, lineHeight: 31, color: tokens.color.onSurface },
  subtitle: { fontSize: 13, color: tokens.color.onSurfaceMuted, marginTop: 2 },
  askOra: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    alignSelf: 'flex-start',
    marginHorizontal: tokens.spacing.lg,
    marginBottom: tokens.spacing.lg,
    minHeight: tokens.touch.min,
    paddingHorizontal: tokens.spacing.xl,
    borderRadius: tokens.radius.md,
    backgroundColor: tokens.color.brand,
  },
  askOraLabel: { color: tokens.color.onBrand, fontSize: 15, fontWeight: '600' },
  tabs: {
    flexDirection: 'row', gap: tokens.spacing.lg,
    paddingHorizontal: tokens.spacing.lg, flexWrap: 'wrap',
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: tokens.color.divider,
  },
  /**
   * The rule under the label is what a person sees; the box around it is what
   * they hit. "File" is 22px of text, so the tappable area is widened and
   * heightened to the 44px floor without touching the type or the spacing —
   * the underline still hugs the word.
   */
  tab: {
    paddingVertical: 11,
    minHeight: tokens.touch.min,
    minWidth: tokens.touch.min,
    alignItems: 'center',
    justifyContent: 'center',
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  tabActive: { borderBottomColor: tokens.color.brand },
  tabText: { color: tokens.color.onSurfaceMuted, fontSize: 14, fontWeight: '500' },
  tabTextActive: { color: tokens.color.onSurface, fontWeight: '600' },
  secondary: {
    marginTop: tokens.spacing.xxl,
    paddingTop: tokens.spacing.lg,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: tokens.color.divider,
  },
  secondaryRow: { flexDirection: 'row', gap: tokens.spacing.md, flexWrap: 'wrap' },
  centerBox: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12, padding: 24 },
  card: { backgroundColor: tokens.color.surface, borderRadius: tokens.radius.lg, padding: tokens.spacing.lg, borderWidth: StyleSheet.hairlineWidth, borderColor: tokens.color.border, gap: 8 },
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
});
