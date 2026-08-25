import * as React from 'react';
import { Modal, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import {
  dayBadge,
  expiryDateLabel,
  expiryLabel,
  statusLabel,
  uploadedLabel,
  type DocItem,
  type SortOrder,
  type StatusFilter,
  SORT_ORDERS,
  STATUS_FILTERS,
} from './libraryView';

/* -------------------------------------------------------------------------- */
/* Header                                                                     */
/* -------------------------------------------------------------------------- */

export function LibraryHeader({ onWhy }: { onWhy: () => void }) {
  const { colors } = useTheme();
  return (
    <View style={styles.header} testID="documents-header">
      <View style={styles.headerText}>
        <Text
          style={[styles.title, { color: colors.textPrimary }]}
          accessibilityRole="header"
          aria-level={1}
        >
          Documenti
        </Text>
        <Text style={[styles.sub, { color: colors.textSecondary }]}>
          I tuoi documenti, organizzati e compresi da ORA.
        </Text>
      </View>
      <Pressable
        onPress={onWhy}
        style={({ pressed }) => [
          styles.whyBtn,
          { backgroundColor: colors.surface, borderColor: colors.border },
          pressed && styles.pressed,
        ]}
        accessibilityRole="button"
        testID="documents-why"
      >
        <Ionicons name="sparkles-outline" size={14} color={colors.accent} />
        <Text style={[styles.whyLabel, { color: colors.textSecondary }]}>Perché conta?</Text>
      </Pressable>
    </View>
  );
}

/**
 * Why ORA keeps documents at all.
 *
 * Four sentences about what the person gets and what stays theirs. No claim
 * the product cannot presently keep — the last line is the one that matters,
 * and it is true because nothing here deletes, shares or acts on a document
 * without being asked.
 */
export function WhyDocumentsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { colors } = useTheme();
  const lines = [
    'ORA legge i documenti che le dai per capire meglio il contesto della tua vita.',
    'Collega le informazioni importanti agli ambiti a cui appartengono.',
    'Quando trova una scadenza, te la tiene a mente.',
    'I documenti restano tuoi: puoi consultarli, usarli con ORA o rimuoverli quando vuoi.',
  ];
  return (
    <Modal visible={open} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable
        style={[styles.scrim, { backgroundColor: colors.scrim }]}
        onPress={onClose}
        accessibilityLabel="Chiudi"
      >
        <View
          style={[
            styles.dialog,
            { backgroundColor: colors.surfaceElevated, borderColor: colors.border },
          ]}
          onStartShouldSetResponder={() => true}
          accessibilityViewIsModal
          testID="documents-why-dialog"
        >
          <View style={styles.dialogHead}>
            <Text
              style={[styles.dialogTitle, { color: colors.textPrimary }]}
              accessibilityRole="header"
              aria-level={2}
            >
              Perché conta
            </Text>
            <Pressable
              onPress={onClose}
              hitSlop={8}
              style={({ pressed }) => [styles.close, pressed && styles.pressed]}
              accessibilityRole="button"
              accessibilityLabel="Chiudi"
              testID="documents-why-close"
            >
              <Ionicons name="close" size={20} color={colors.textTertiary} />
            </Pressable>
          </View>
          {lines.map((l) => (
            <Text key={l} style={[styles.dialogLine, { color: colors.textSecondary }]}>
              {l}
            </Text>
          ))}
        </View>
      </Pressable>
    </Modal>
  );
}

/* -------------------------------------------------------------------------- */
/* Action area                                                                */
/* -------------------------------------------------------------------------- */

/**
 * What a person can actually do here.
 *
 * The reference composition has four cards; this shows the ones that are real.
 * A scanner and an import-from-connected-apps tile would look right and do
 * nothing, and a dead affordance on the first row of a page is worse than a
 * shorter row.
 */
export function ActionCard({
  icon,
  title,
  detail,
  cta,
  onPress,
  busy,
  testID,
}: {
  icon: React.ComponentProps<typeof Ionicons>['name'];
  title: string;
  detail: string;
  cta: string;
  onPress: () => void;
  busy?: boolean;
  testID?: string;
}) {
  const { colors } = useTheme();
  return (
    <View
      style={[styles.actionCard, { backgroundColor: colors.surface, borderColor: colors.border }]}
      testID={testID}
    >
      <View style={styles.actionHead}>
        <Ionicons name={icon} size={19} color={colors.accent} />
        <Text style={[styles.actionTitle, { color: colors.textPrimary }]} numberOfLines={1}>
          {title}
        </Text>
      </View>
      <Text style={[styles.actionDetail, { color: colors.textSecondary }]} numberOfLines={2}>
        {detail}
      </Text>
      <Pressable
        onPress={onPress}
        disabled={busy}
        style={({ pressed }) => [
          styles.actionCta,
          { backgroundColor: colors.accent },
          (pressed || busy) && styles.pressed,
        ]}
        accessibilityRole="button"
        accessibilityLabel={`${cta}: ${title}`}
        testID={testID ? `${testID}-cta` : undefined}
      >
        <Text style={[styles.actionCtaLabel, { color: colors.onAccent }]}>{cta}</Text>
      </Pressable>
    </View>
  );
}

/* -------------------------------------------------------------------------- */
/* Search + filters                                                           */
/* -------------------------------------------------------------------------- */

function Select<T extends string>({
  value,
  options,
  onChange,
  testID,
}: {
  value: T;
  options: Array<{ id: T; label: string }>;
  onChange: (v: T) => void;
  testID?: string;
}) {
  const { colors } = useTheme();
  const [open, setOpen] = React.useState(false);
  const current = options.find((o) => o.id === value) || options[0];
  return (
    <View style={styles.selectWrap}>
      <Pressable
        onPress={() => setOpen((v) => !v)}
        style={({ pressed }) => [
          styles.control,
          { backgroundColor: colors.surface, borderColor: colors.border },
          pressed && styles.pressed,
        ]}
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        testID={testID}
      >
        <Text style={[styles.controlLabel, { color: colors.textPrimary }]} numberOfLines={1}>
          {current?.label}
        </Text>
        <Ionicons name={open ? 'chevron-up' : 'chevron-down'} size={15} color={colors.textTertiary} />
      </Pressable>
      {open ? (
        <View
          style={[
            styles.menu,
            { backgroundColor: colors.surfaceElevated, borderColor: colors.border },
          ]}
        >
          {options.map((o) => (
            <Pressable
              key={o.id}
              onPress={() => {
                onChange(o.id);
                setOpen(false);
              }}
              style={({ pressed, hovered }: any) => [
                styles.menuItem,
                (hovered || o.id === value) && { backgroundColor: colors.backgroundSecondary },
                pressed && styles.pressed,
              ]}
              accessibilityRole="button"
              accessibilityState={{ selected: o.id === value }}
              testID={testID ? `${testID}-${o.id}` : undefined}
            >
              <Text style={[styles.menuLabel, { color: colors.textPrimary }]}>{o.label}</Text>
              {o.id === value ? (
                <Ionicons name="checkmark" size={15} color={colors.accent} />
              ) : null}
            </Pressable>
          ))}
        </View>
      ) : null}
    </View>
  );
}

export function LibraryControls({
  query,
  onQuery,
  kind,
  kinds,
  onKind,
  status,
  onStatus,
  order,
  onOrder,
}: {
  query: string;
  onQuery: (v: string) => void;
  kind: string;
  kinds: string[];
  onKind: (v: string) => void;
  status: StatusFilter;
  onStatus: (v: StatusFilter) => void;
  order: SortOrder;
  onOrder: (v: SortOrder) => void;
}) {
  const { colors } = useTheme();
  const kindOptions = [{ id: 'all', label: 'Tutti i tipi' }, ...kinds.map((k) => ({ id: k, label: k }))];
  return (
    <View style={styles.controls} testID="documents-controls">
      <View
        style={[styles.search, { backgroundColor: colors.surface, borderColor: colors.border }]}
      >
        <Ionicons name="search" size={16} color={colors.textTertiary} />
        <TextInput
          value={query}
          onChangeText={onQuery}
          // Names exactly what this box looks through — the payload already on
          // screen. Promising content search here would be a promise a filter
          // over a loaded list cannot keep.
          placeholder="Cerca per nome, tipo o riepilogo…"
          placeholderTextColor={colors.placeholder || colors.textTertiary}
          style={[styles.searchInput, { color: colors.textPrimary }]}
          accessibilityLabel="Cerca documenti"
          testID="documents-search"
        />
        {query ? (
          <Pressable
            onPress={() => onQuery('')}
            hitSlop={8}
            accessibilityRole="button"
            accessibilityLabel="Cancella ricerca"
            testID="documents-search-clear"
          >
            <Ionicons name="close-circle" size={16} color={colors.textTertiary} />
          </Pressable>
        ) : null}
      </View>
      <Select value={kind} options={kindOptions} onChange={onKind} testID="documents-kind" />
      <Select value={status} options={STATUS_FILTERS} onChange={onStatus} testID="documents-status" />
      <Select value={order} options={SORT_ORDERS} onChange={onOrder} testID="documents-order" />
    </View>
  );
}

/* -------------------------------------------------------------------------- */
/* Document row                                                               */
/* -------------------------------------------------------------------------- */

const KIND_ICON: Record<string, React.ComponentProps<typeof Ionicons>['name']> = {
  PDF: 'document-text',
  DOCX: 'document-text',
  DOC: 'document-text',
  XLSX: 'grid',
  XLS: 'grid',
  CSV: 'grid',
  PPTX: 'easel',
  Immagine: 'image',
  Testo: 'document-text',
};

/**
 * One document, as something a person recognises.
 *
 * Title, what kind of file and when it arrived, whether ORA has a summary, the
 * parts of life it belongs to, and the one thing that matters most about its
 * state — with an expiry taking precedence over the analysis badge, because a
 * date that is running out is more urgent than whether the reading finished.
 * Status is never colour alone: every state carries its own icon and its own
 * words.
 */
export function DocumentRow({
  item,
  onOpen,
  first,
  compact,
}: {
  item: DocItem;
  onOpen: () => void;
  first?: boolean;
  /** Narrow screen: the row stacks instead of competing for width. */
  compact?: boolean;
}) {
  const { colors } = useTheme();
  const expiring = item.expiry ? expiryDateLabel(item.expiry.at) : null;
  const countdown = item.expiry ? expiryLabel(item.expiry.at) : null;
  const label = statusLabel(item.status);

  const tone =
    item.status === 'ready'
      ? { icon: 'checkmark-circle' as const, color: colors.success }
      : item.status === 'failed'
        ? { icon: 'alert-circle-outline' as const, color: colors.error }
        : item.status === 'needs_review'
          ? { icon: 'alert-circle-outline' as const, color: colors.warning }
          : item.status === 'analyzing'
            ? { icon: 'sync-outline' as const, color: colors.textTertiary }
            : { icon: 'ellipse-outline' as const, color: colors.textTertiary };

  // A running-out date outranks the reading state: it is the more urgent fact
  // about the document, and only one of the two fits on a row.
  const status = expiring ? (
    <View style={styles.statusInline}>
      <Ionicons name="alert-circle-outline" size={16} color={colors.warning} />
      <Text style={[styles.statusLabel, { color: colors.warning }]} numberOfLines={1}>
        {expiring}
      </Text>
    </View>
  ) : (
    <View style={styles.statusInline}>
      <Ionicons name={tone.icon} size={16} color={tone.color} />
      <Text style={[styles.statusLabel, { color: colors.textSecondary }]} numberOfLines={1}>
        {label}
      </Text>
    </View>
  );

  const areaChips = item.areas?.length ? (
    <View style={styles.areaRow}>
      {item.areas.slice(0, 2).map((a) => (
        <View key={a.key} style={[styles.areaChip, { backgroundColor: colors.backgroundSecondary }]}>
          <Text style={[styles.areaLabel, { color: colors.textSecondary }]} numberOfLines={1}>
            {a.label}
          </Text>
        </View>
      ))}
    </View>
  ) : null;

  return (
    <Pressable
      onPress={onOpen}
      style={({ pressed, hovered }: any) => [
        styles.row,
        !first && { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.divider },
        hovered && { backgroundColor: colors.backgroundSecondary },
        pressed && styles.pressed,
      ]}
      accessibilityRole="button"
      accessibilityLabel={`${item.title}. ${expiring || label}`}
      testID={`document-row-${item.id}`}
    >
      <View style={[styles.rowIcon, { backgroundColor: colors.backgroundSecondary }]}>
        <Ionicons
          name={KIND_ICON[item.kind] || 'document-outline'}
          size={18}
          color={colors.textSecondary}
        />
      </View>

      <View style={styles.rowBody}>
        <Text
          style={[styles.rowTitle, { color: colors.textPrimary }]}
          numberOfLines={compact ? 2 : 1}
        >
          {item.title}
        </Text>
        <Text style={[styles.rowMeta, { color: colors.textSecondary }]} numberOfLines={1}>
          {[item.kind, uploadedLabel(item.uploaded_at) ? `Caricato il ${uploadedLabel(item.uploaded_at)}` : null]
            .filter(Boolean)
            .join(' · ')}
        </Text>
        <Text style={[styles.rowSummary, { color: colors.textTertiary }]} numberOfLines={1}>
          {item.summary ? 'Riepilogo disponibile' : 'Nessun riepilogo'}
        </Text>
        {countdown && countdown !== 'Scaduta' ? (
          <Text style={[styles.rowCountdown, { color: colors.warning }]}>{countdown}</Text>
        ) : null}

        {/*
          On a narrow screen the areas and the state move below the title
          rather than beside it. Three columns fighting over 390px turned the
          title into two letters and an ellipsis — the one thing on the row a
          person actually reads.
        */}
        {compact ? (
          <View style={styles.compactMeta}>
            {status}
            {areaChips}
          </View>
        ) : null}
      </View>

      {!compact ? areaChips : null}
      {!compact ? <View style={styles.rowStatus}>{status}</View> : null}

      <Ionicons name="chevron-forward" size={16} color={colors.textTertiary} />
    </Pressable>
  );
}

/* -------------------------------------------------------------------------- */
/* Right rail                                                                 */
/* -------------------------------------------------------------------------- */

export function Panel({
  title,
  children,
  testID,
}: {
  title: string;
  children: React.ReactNode;
  testID?: string;
}) {
  const { colors } = useTheme();
  const present = React.Children.toArray(children).filter(Boolean);
  if (!present.length) return null;
  return (
    <View
      style={[styles.panel, { backgroundColor: colors.surface, borderColor: colors.border }]}
      testID={testID}
    >
      <Text style={[styles.panelTitle, { color: colors.textPrimary }]}>{title}</Text>
      {children}
    </View>
  );
}

const SUMMARY_ICONS: Record<string, React.ComponentProps<typeof Ionicons>['name']> = {
  all: 'documents-outline',
  ready: 'checkmark-circle-outline',
  waiting: 'time-outline',
  expiring: 'alert-circle-outline',
  actions: 'sparkles-outline',
  failed: 'close-circle-outline',
};

export function SummaryPanel({
  rows,
}: {
  rows: Array<{ label: string; value: number; icon?: string }>;
}) {
  const { colors } = useTheme();
  if (!rows.length) return null;
  return (
    <Panel title="IN SINTESI" testID="documents-summary">
      {rows.map((r) => (
        <View key={r.label} style={styles.summaryRow}>
          <Ionicons
            name={SUMMARY_ICONS[r.icon || ''] || 'ellipse-outline'}
            size={16}
            color={colors.accent}
          />
          <Text style={[styles.summaryLabel, { color: colors.textSecondary }]} numberOfLines={1}>
            {r.label}
          </Text>
          <Text style={[styles.summaryValue, { color: colors.textPrimary }]}>{r.value}</Text>
        </View>
      ))}
    </Panel>
  );
}

export function ExpiringPanel({
  expiring,
  onOpen,
}: {
  expiring: Array<{ id: string; title: string; at: string }>;
  onOpen: (id: string) => void;
}) {
  const { colors } = useTheme();
  if (!expiring.length) return null;
  return (
    <Panel title="IN SCADENZA" testID="documents-expiring">
      {expiring.map((e) => {
        const badge = dayBadge(e.at);
        return (
          <Pressable
            key={e.id}
            onPress={() => onOpen(e.id)}
            style={({ pressed }) => [styles.railRow, pressed && styles.pressed]}
            accessibilityRole="button"
            accessibilityLabel={e.title}
            testID={`documents-expiring-${e.id}`}
          >
            {badge ? (
              <View style={styles.dateBadge}>
                <Text style={[styles.dateDay, { color: colors.textPrimary }]}>{badge.day}</Text>
                <Text style={[styles.dateMonth, { color: colors.textTertiary }]}>{badge.month}</Text>
              </View>
            ) : null}
            <View style={styles.rowBody}>
              <Text style={[styles.railTitle, { color: colors.textPrimary }]} numberOfLines={2}>
                {e.title}
              </Text>
              <Text style={[styles.railMeta, { color: colors.warning }]}>{expiryLabel(e.at)}</Text>
            </View>
            <Ionicons name="chevron-forward" size={15} color={colors.textTertiary} />
          </Pressable>
        );
      })}
    </Panel>
  );
}

/**
 * What ORA can do with a document — only what it genuinely does today.
 *
 * Every line here maps to something already shipped: the extractor persists
 * deadlines, the analysis writes a summary, a document can be attached to a
 * conversation as context, and the Life Profile links it to an area. Nothing
 * aspirational.
 */
export function CapabilitiesPanel() {
  const { colors } = useTheme();
  const rows: Array<{ icon: React.ComponentProps<typeof Ionicons>['name']; label: string }> = [
    { icon: 'calendar-outline', label: 'Tiene a mente le scadenze che trova' },
    { icon: 'reader-outline', label: 'Riassume cosa contiene' },
    { icon: 'chatbubble-ellipses-outline', label: 'Risponde alle tue domande sul documento' },
    { icon: 'layers-outline', label: 'Lo collega alla parte di vita a cui appartiene' },
  ];
  return (
    <Panel title="COSA PUÒ FARE ORA CON I TUOI DOCUMENTI" testID="documents-capabilities">
      {rows.map((r) => (
        <View key={r.label} style={styles.capRow}>
          <Ionicons name={r.icon} size={16} color={colors.textTertiary} />
          <Text style={[styles.capLabel, { color: colors.textSecondary }]}>{r.label}</Text>
        </View>
      ))}
    </Panel>
  );
}

/* -------------------------------------------------------------------------- */
/* States                                                                     */
/* -------------------------------------------------------------------------- */

export function LibraryEmpty({ onUpload, busy }: { onUpload: () => void; busy?: boolean }) {
  const { colors } = useTheme();
  return (
    <View style={styles.empty} testID="documents-empty">
      <Text style={[styles.emptyTitle, { color: colors.textPrimary }]}>
        Qui puoi tenere i documenti che vuoi usare con ORA.
      </Text>
      <Text style={[styles.emptyBody, { color: colors.textSecondary }]}>
        ORA può aiutarti a capirli e tenere a mente le informazioni importanti.
      </Text>
      <Pressable
        onPress={onUpload}
        disabled={busy}
        style={({ pressed }) => [
          styles.emptyCta,
          { backgroundColor: colors.accent },
          (pressed || busy) && styles.pressed,
        ]}
        accessibilityRole="button"
        testID="documents-empty-cta"
      >
        <Text style={[styles.emptyCtaLabel, { color: colors.onAccent }]}>Carica un documento</Text>
      </Pressable>
    </View>
  );
}

/** No document matches the controls — a different thing from having none. */
export function NoMatches({ onReset }: { onReset: () => void }) {
  const { colors } = useTheme();
  return (
    <View style={styles.noMatch} testID="documents-no-match">
      <Text style={[styles.noMatchText, { color: colors.textSecondary }]}>
        Nessun documento corrisponde a questa ricerca.
      </Text>
      <Pressable
        onPress={onReset}
        style={({ pressed }) => [styles.noMatchBtn, { borderColor: colors.border }, pressed && styles.pressed]}
        accessibilityRole="button"
        testID="documents-reset"
      >
        <Text style={[styles.noMatchBtnLabel, { color: colors.textPrimary }]}>Azzera i filtri</Text>
      </Pressable>
    </View>
  );
}

export function LibrarySkeleton({ wide }: { wide: boolean }) {
  const { colors } = useTheme();
  const box = (h: number) => (
    <View
      style={[
        styles.skBox,
        { backgroundColor: colors.surface, borderColor: colors.border, minHeight: h },
      ]}
    />
  );
  const bar = (w: any, h = 12) => (
    <View style={{ width: w, height: h, borderRadius: 6, backgroundColor: colors.skeleton }} />
  );
  return (
    <View style={styles.skeleton} testID="documents-skeleton">
      <View style={styles.skHead}>
        {bar(150, 28)}
        {bar('45%')}
      </View>
      <View style={wide ? styles.skRow : undefined}>
        <View style={[styles.skMain, wide && styles.skFlex]}>
          <View style={styles.skTriple}>
            {box(150)}
            {box(150)}
          </View>
          {box(56)}
          {box(420)}
        </View>
        {wide ? (
          <View style={styles.skRail}>
            {box(180)}
            {box(150)}
          </View>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'flex-start', gap: tokens.spacing.lg },
  headerText: { flex: 1, gap: 4 },
  title: { fontSize: 30, fontWeight: '700', letterSpacing: -0.8, lineHeight: 37 },
  sub: { fontSize: 15, lineHeight: 21, maxWidth: 520 },
  whyBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 7,
    borderWidth: StyleSheet.hairlineWidth, borderRadius: tokens.radius.md,
    paddingHorizontal: tokens.spacing.lg, minHeight: tokens.touch.min,
  },
  whyLabel: { fontSize: 13, fontWeight: '500' },

  scrim: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: tokens.spacing.xl },
  dialog: {
    width: 460, maxWidth: '100%',
    borderRadius: tokens.radius.xl, borderWidth: StyleSheet.hairlineWidth,
    padding: tokens.spacing.xl, gap: tokens.spacing.md,
  },
  dialogHead: { flexDirection: 'row', alignItems: 'flex-start', gap: tokens.spacing.md },
  dialogTitle: { fontSize: 19, fontWeight: '700', flex: 1, letterSpacing: -0.3 },
  close: {
    width: tokens.touch.min, height: tokens.touch.min,
    alignItems: 'center', justifyContent: 'center', marginTop: -10, marginRight: -12,
  },
  dialogLine: { fontSize: 14, lineHeight: 21 },

  /**
   * Sized like the cards in the reference rather than stretched to fill the
   * row. Only the capabilities that genuinely exist are shown, so there are
   * fewer of them than the composition allows for — letting two cards expand
   * across the whole width would make the page look like it was designed for
   * exactly two, instead of like a row with room for more.
   */
  actionCard: {
    flexGrow: 0, flexShrink: 1, flexBasis: 260, minWidth: 220, maxWidth: 300,
    borderRadius: tokens.radius.lg, borderWidth: StyleSheet.hairlineWidth,
    padding: tokens.spacing.lg, gap: 6,
  },
  actionHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  actionTitle: { fontSize: 15, fontWeight: '650' as any, flex: 1 },
  actionDetail: { fontSize: 12, lineHeight: 17, minHeight: 34 },
  actionCta: {
    alignSelf: 'flex-start', minHeight: tokens.touch.min, justifyContent: 'center',
    paddingHorizontal: tokens.spacing.lg, borderRadius: tokens.radius.md, marginTop: 4,
  },
  actionCtaLabel: { fontSize: 13, fontWeight: '600' },

  controls: { flexDirection: 'row', gap: tokens.spacing.md, alignItems: 'center', flexWrap: 'wrap', zIndex: 10 },
  search: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    flexGrow: 1, flexBasis: 240, minWidth: 200,
    borderWidth: StyleSheet.hairlineWidth, borderRadius: tokens.radius.md,
    paddingHorizontal: tokens.spacing.md, minHeight: tokens.touch.min,
  },
  searchInput: { flex: 1, fontSize: 14, minHeight: tokens.touch.min },
  selectWrap: { position: 'relative', zIndex: 20 },
  control: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    borderWidth: StyleSheet.hairlineWidth, borderRadius: tokens.radius.md,
    paddingHorizontal: tokens.spacing.md, minHeight: tokens.touch.min, maxWidth: 180,
  },
  controlLabel: { fontSize: 13, flexShrink: 1 },
  menu: {
    position: 'absolute', top: 48, right: 0, minWidth: 180,
    borderRadius: tokens.radius.md, borderWidth: StyleSheet.hairlineWidth,
    paddingVertical: 4, zIndex: 30,
  },
  menuItem: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingHorizontal: tokens.spacing.md, minHeight: 40,
  },
  menuLabel: { fontSize: 13, flex: 1 },

  row: {
    flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.md,
    paddingHorizontal: tokens.spacing.lg, paddingVertical: tokens.spacing.md,
    minHeight: 76,
  },
  rowIcon: {
    width: 38, height: 38, borderRadius: tokens.radius.sm,
    alignItems: 'center', justifyContent: 'center',
  },
  rowBody: { flex: 1, minWidth: 0, gap: 1 },
  rowTitle: { fontSize: 15, fontWeight: '600' },
  rowMeta: { fontSize: 12, lineHeight: 17 },
  rowSummary: { fontSize: 12, lineHeight: 17 },
  rowCountdown: { fontSize: 12, fontWeight: '600', marginTop: 1 },
  areaRow: { flexDirection: 'row', gap: 6, flexShrink: 0 },
  areaChip: {
    borderRadius: tokens.radius.sm, paddingHorizontal: 9, paddingVertical: 4, maxWidth: 110,
  },
  areaLabel: { fontSize: 12 },
  rowStatus: { minWidth: 130, flexShrink: 0 },
  statusInline: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  compactMeta: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginTop: 4 },
  statusLabel: { fontSize: 13, flexShrink: 1 },

  panel: {
    borderRadius: tokens.radius.lg, borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: tokens.spacing.lg, paddingVertical: tokens.spacing.md, gap: 2,
  },
  panelTitle: {
    fontSize: 11, fontWeight: '700', letterSpacing: 1.1,
    paddingVertical: tokens.spacing.sm,
  },
  summaryRow: { flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 38 },
  summaryLabel: { fontSize: 13, flex: 1 },
  summaryValue: { fontSize: 16, fontWeight: '700' },
  railRow: {
    flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.md,
    paddingVertical: tokens.spacing.sm, minHeight: tokens.touch.min,
  },
  railTitle: { fontSize: 14, fontWeight: '500', lineHeight: 19 },
  railMeta: { fontSize: 12 },
  dateBadge: { width: 34, alignItems: 'center' },
  dateDay: { fontSize: 16, fontWeight: '700', lineHeight: 20 },
  dateMonth: { fontSize: 10, fontWeight: '700', letterSpacing: 0.6 },
  capRow: { flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 34 },
  capLabel: { fontSize: 13, flex: 1, lineHeight: 18 },

  empty: { gap: 8, paddingVertical: tokens.spacing.xxxl, maxWidth: 520 },
  emptyTitle: { fontSize: 22, fontWeight: '700', letterSpacing: -0.5, lineHeight: 29 },
  emptyBody: { fontSize: 15, lineHeight: 22 },
  emptyCta: {
    alignSelf: 'flex-start', minHeight: tokens.touch.min, justifyContent: 'center',
    paddingHorizontal: tokens.spacing.xl, borderRadius: tokens.radius.md,
    marginTop: tokens.spacing.md,
  },
  emptyCtaLabel: { fontSize: 15, fontWeight: '600' },
  noMatch: { padding: tokens.spacing.xl, gap: tokens.spacing.md, alignItems: 'flex-start' },
  noMatchText: { fontSize: 14, lineHeight: 20 },
  noMatchBtn: {
    minHeight: 40, justifyContent: 'center', paddingHorizontal: tokens.spacing.lg,
    borderRadius: tokens.radius.md, borderWidth: StyleSheet.hairlineWidth,
  },
  noMatchBtnLabel: { fontSize: 13, fontWeight: '600' },

  skeleton: { gap: tokens.spacing.xl },
  skHead: { gap: tokens.spacing.sm },
  skRow: { flexDirection: 'row', gap: tokens.spacing.xl, alignItems: 'flex-start' },
  skMain: { gap: tokens.spacing.lg },
  skFlex: { flex: 1 },
  skRail: { width: 300, gap: tokens.spacing.lg },
  skTriple: { flexDirection: 'row', gap: tokens.spacing.md },
  skBox: { flex: 1, borderRadius: tokens.radius.lg, borderWidth: StyleSheet.hairlineWidth },
  pressed: { opacity: 0.75 },
});
