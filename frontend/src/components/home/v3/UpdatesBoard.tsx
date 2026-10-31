/**
 * Aggiornamenti di ORA — la stessa bacheca in Home e nella pagina.
 *
 *     TRE DOMANDE, SEMPRE NELLO STESSO ORDINE:
 *     DEVO FARE QUALCOSA ADESSO? SERVE UNA MIA RISPOSTA? CHE COSA STA SEGUENDO ORA?
 *
 * Approvata dal proprietario il 23/10/2026 (bozza «Giornata normale» /
 * «Quando serve agire»). Ogni scheda: un titolo corto, il dato che conta in
 * grande, al massimo due bottoni. Nessun dato inventato: ciò che una sorgente
 * non dice non compare. Le Situazioni mostrano la stima di ORA, i valori
 * dell'ultima lettura meteo davvero eseguita e il prossimo controllo.
 */
import React, { useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import type { MonitoredSituation } from '@/src/api/client';
import { useTheme } from '@/src/theme/ThemeProvider';
import type { Aggiornamento } from './aggiornamenti';
import { agoLabel } from './homeItemView';
import { ORDINE, TITOLI, raggruppa, type GruppoAggiornamento } from './gruppiAggiornamenti';

export { gruppoDi, raggruppa, sintesiAggiornamenti } from './gruppiAggiornamenti';

type Filtro = 'tutti' | 'per_te' | 'in_corso';

export function UpdatesBoard({
  righe,
  onOpen,
  onDismiss,
  canDismiss,
  testIdFor,
  limit,
  showFilters = true,
  showNote = true,
}: {
  righe: Aggiornamento[];
  onOpen: (a: Aggiornamento) => void;
  /** Assente per gli aggiornamenti che non si possono rimuovere da qui. */
  onDismiss?: (a: Aggiornamento) => void | Promise<void>;
  /** Se un aggiornamento si può davvero rimuovere da qui (niente bottoni morti). */
  canDismiss?: (a: Aggiornamento) => boolean;
  /** Identificativi stabili per i test e l'accessibilità. */
  testIdFor?: (a: Aggiornamento) => string;
  /** Quante schede al massimo (la Home ne mostra poche). */
  limit?: number;
  showFilters?: boolean;
  showNote?: boolean;
}) {
  const { colors } = useTheme();
  const [filtro, setFiltro] = useState<Filtro>('tutti');
  const gruppi = useMemo(() => raggruppa(righe), [righe]);
  const perTe = gruppi.adesso.length + gruppi.per_te.length;
  const inCorso = gruppi.in_corso.length;

  let restanti = typeof limit === 'number' ? limit : Number.POSITIVE_INFINITY;
  const visibili = ORDINE.filter((g) =>
    filtro === 'tutti' || (filtro === 'per_te' ? g === 'adesso' || g === 'per_te' : g === 'in_corso'),
  ).map((g) => {
    const elenco = gruppi[g].slice(0, Math.max(0, restanti));
    restanti -= elenco.length;
    return [g, elenco] as const;
  }).filter(([, elenco]) => elenco.length > 0);

  return (
    <View style={styles.board} testID="updates-board">
      {showFilters && (perTe || inCorso) ? (
        <View style={styles.chips} accessibilityRole="tablist">
          {([
            ['tutti', 'Tutti', null],
            ['per_te', 'Per te', perTe],
            ['in_corso', 'In corso', inCorso],
          ] as const).map(([key, label, count]) => {
            const on = filtro === key;
            return (
              <Pressable
                key={key}
                onPress={() => setFiltro(key)}
                accessibilityRole="tab"
                accessibilityState={{ selected: on }}
                style={[styles.chip, {
                  backgroundColor: on ? colors.textPrimary : colors.surface,
                  borderColor: on ? colors.textPrimary : colors.border,
                }]}
                testID={`updates-filter-${key}`}
              >
                <Text style={[styles.chipText, { color: on ? colors.surface : colors.textSecondary }]}>
                  {label}{count ? <Text style={styles.chipCount}>{` ${count}`}</Text> : null}
                </Text>
              </Pressable>
            );
          })}
        </View>
      ) : null}

      {visibili.map(([g, elenco]) => (
        <View key={g} testID={`updates-group-${g}`}>
          <Text style={[styles.section, { color: colors.textTertiary }]} accessibilityRole="header">
            {TITOLI[g].toUpperCase()}
          </Text>
          {elenco.map((a) =>
            a.situazione ? (
              <SituationCard
                key={a.id}
                a={a}
                s={a.situazione}
                urgent={g === 'adesso'}
                onOpen={onOpen}
                onDismiss={onDismiss && (canDismiss ? canDismiss(a) : true) ? onDismiss : undefined}
                testID={testIdFor ? testIdFor(a) : `update-${a.id}`}
              />
            ) : (
              <UpdateCard
                key={a.id}
                a={a}
                gruppo={g}
                onOpen={onOpen}
                onDismiss={onDismiss && (canDismiss ? canDismiss(a) : true) ? onDismiss : undefined}
                testID={testIdFor ? testIdFor(a) : `update-${a.id}`}
              />
            ),
          )}
        </View>
      ))}

      {showNote ? (
        <Text style={[styles.note, { color: colors.textTertiary }]}>
          Ciò che è scaduto o fermo da tre giorni sparisce da solo.
        </Text>
      ) : null}
    </View>
  );
}

/* -------------------------------------------------------------------------- */

const ICONE: Record<Aggiornamento['genere'], keyof typeof Ionicons.glyphMap> = {
  lavoro: 'sync-outline',
  occasione: 'eye-outline',
  suggerimento: 'bulb-outline',
  spunto: 'information-circle-outline',
};

function etichetta(a: Aggiornamento, g: GruppoAggiornamento): string | null {
  if (g === 'adesso') return 'Adesso';
  if (g !== 'per_te') return null;
  if (a.genere === 'suggerimento') return a.stato || 'Una proposta';
  if (a.promemoria === 'reminder') return 'Promemoria';
  if (a.promemoria === 'phone_call') return 'Telefonata';
  if (a.promemoria === 'morning_brief') return 'Il punto del mattino';
  if (a.promemoria === 'evening_brief') return 'Domani';
  if (a.promemoria === 'ora_check') return 'Controllo di ORA';
  if (a.promemoria === 'habit') return 'Proposta';
  if (a.genere === 'occasione') return 'Da confermare';
  return 'Serve una risposta';
}

function UpdateCard({
  a, gruppo, onOpen, onDismiss, testID,
}: {
  a: Aggiornamento;
  gruppo: GruppoAggiornamento;
  onOpen: (a: Aggiornamento) => void;
  onDismiss?: (a: Aggiornamento) => void | Promise<void>;
  testID: string;
}) {
  const { colors } = useTheme();
  const [busy, setBusy] = useState(false);
  const tag = etichetta(a, gruppo);
  const urgent = gruppo === 'adesso';
  const tone = urgent
    ? { fg: colors.error, bg: colors.errorBg }
    : gruppo === 'per_te'
      ? { fg: colors.warning, bg: colors.warningBg }
      : { fg: colors.accent, bg: colors.accentMuted };
  const sotto = (a.cosa_serve || a.perche || a.cosa_sta_facendo || '').trim();
  const quando = agoLabel(a.quando);
  const conBottoni = gruppo === 'per_te' || gruppo === 'adesso';

  const dismiss = async () => {
    if (!onDismiss || busy) return;
    setBusy(true);
    try { await onDismiss(a); } finally { setBusy(false); }
  };

  return (
    <Pressable
      onPress={() => onOpen(a)}
      accessibilityRole="button"
      accessibilityLabel={`Apri: ${a.cosa}`}
      style={({ pressed }) => [
        styles.card,
        { backgroundColor: urgent ? colors.errorBg : colors.surface, borderColor: urgent ? colors.error : colors.divider },
        pressed && styles.pressed,
      ]}
      testID={testID}
    >
      <View style={styles.row}>
        <View style={[styles.icon, { backgroundColor: urgent ? colors.surface : tone.bg }]}>
          <Ionicons name={a.promemoria === 'reminder' ? 'alarm-outline' : a.promemoria === 'phone_call' ? 'call-outline' : a.promemoria === 'morning_brief' ? 'sunny-outline' : a.promemoria === 'evening_brief' ? 'moon-outline' : a.promemoria === 'ora_check' ? 'pulse-outline' : a.promemoria === 'habit' ? 'repeat-outline' : ICONE[a.genere]} size={20} color={tone.fg} />
        </View>
        <View style={styles.body}>
          {tag || quando ? (
            <View style={styles.tagRow}>
              {tag ? (
                <Text style={[styles.tag, { backgroundColor: urgent ? colors.surface : tone.bg, color: tone.fg }]}>{tag}</Text>
              ) : <View />}
              {quando ? <Text style={[styles.ago, { color: colors.textTertiary }]}>{quando}</Text> : null}
            </View>
          ) : null}
          <Text style={[styles.title, { color: colors.textPrimary }]} numberOfLines={3}>{a.cosa}</Text>
          {sotto ? (
            <Text style={[styles.meta, { color: colors.textSecondary }]} numberOfLines={2}>{sotto}</Text>
          ) : null}
        </View>
      </View>
      {conBottoni ? (
        <View style={styles.actions}>
          <Pressable
            onPress={() => onOpen(a)}
            accessibilityRole="button"
            style={({ pressed }) => [styles.btn, { backgroundColor: urgent ? colors.error : colors.accent }, pressed && styles.pressed]}
            testID={`${testID}-apri`}
          >
            <Text style={[styles.btnText, { color: colors.onAccent }]}>
              {urgent ? 'Apri' : a.cosa_serve ? 'Rispondi' : 'Rivedi'}
            </Text>
          </Pressable>
          {onDismiss ? (
            <Pressable
              onPress={() => void dismiss()}
              disabled={busy}
              accessibilityRole="button"
              accessibilityLabel={`Ignora: ${a.cosa}`}
              style={({ pressed }) => [styles.btn, { backgroundColor: colors.backgroundPrimary }, pressed && styles.pressed]}
              testID={`${testID}-rimuovi`}
            >
              <Text style={[styles.btnText, { color: colors.textSecondary }]}>{busy ? 'Rimozione…' : 'Ignora'}</Text>
            </Pressable>
          ) : null}
        </View>
      ) : null}
    </Pressable>
  );
}

/* -------------------------------------------------------------------------- */

function ora(iso?: string | null): string | null {
  if (!iso) return null;
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return null;
  return at.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
}

function numero(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

function SituationCard({
  a, s, urgent, onOpen, onDismiss, testID,
}: {
  a: Aggiornamento;
  s: MonitoredSituation;
  urgent: boolean;
  onOpen: (a: Aggiornamento) => void;
  onDismiss?: (a: Aggiornamento) => void | Promise<void>;
  testID: string;
}) {
  const { colors } = useTheme();
  const esito = s.outcome || null;
  const iniziata = ora(s.started_at);
  const luogo = (s.location_label || '').trim();
  const c = s.conditions || null;
  const fatti: string[] = [];
  if (c) {
    const t = numero(c.temperature_c); if (t !== null) fatti.push(`${Math.round(t)}°`);
    const h = numero(c.humidity_pct); if (h !== null) fatti.push(`Umidità ${Math.round(h)}%`);
    const w = numero(c.wind_kmh); if (w !== null) fatti.push(`Vento ${Math.round(w)} km/h`);
    const r = numero(c.rain_chance_max_pct); if (r !== null) fatti.push(`Pioggia ${Math.round(r)}%`);
  }
  const prossimo = s.next_check_label || ora(s.next_check_at);
  const grande = esito?.headline
    || (s.expected_outcome || '').trim()
    || (s.followup_status === 'scheduled' || s.followup_status === 'due' || s.followup_status === 'running'
      ? 'Sto preparando la stima'
      // The technical diagnosis belongs to the detail page. Owner screenshot
      // 24/10 18:37: "La situazione è registrata e il lavoro esiste, ma non
      // risulta una prossima esecuzione confermata." as the card's headline.
      : s.followup_status === 'not_scheduled' || s.followup_status === 'recovery_pending'
        ? 'Sto riprendendo il controllo'
        : 'Situazione in osservazione');
  const spiegazione = esito
    ? (esito.basis === 'missing_information'
      ? 'Mi manca un dato per stimare'
      : esito.window_label ? `Finestra stimata: ${esito.window_label}` : 'Stima di ORA sulle fonti lette')
    : null;

  // Barra del tempo: solo con un inizio reale e almeno un punto futuro reale.
  const t0 = s.started_at ? Date.parse(s.started_at) : NaN;
  const tCheck = s.next_check_at ? Date.parse(s.next_check_at) : NaN;
  const tWin0 = esito?.window_start ? Date.parse(esito.window_start) : NaN;
  const tWin1 = esito?.window_end ? Date.parse(esito.window_end) : NaN;
  const tNow = Date.now();
  const fine = Math.max(...[tCheck, tWin1, tWin0, tNow].filter((x) => Number.isFinite(x)));
  const barra = Number.isFinite(t0) && fine > t0 && (Number.isFinite(tCheck) || Number.isFinite(tWin0));
  const pct = (t: number) => `${Math.min(100, Math.max(0, ((t - t0) / (fine - t0)) * 100))}%` as const;

  return (
    <Pressable
      onPress={() => onOpen(a)}
      accessibilityRole="button"
      accessibilityLabel={`Apri: ${s.summary}`}
      style={({ pressed }) => [
        styles.card,
        { backgroundColor: urgent ? colors.errorBg : colors.surface, borderColor: urgent ? colors.error : colors.divider },
        pressed && styles.pressed,
      ]}
      testID={testID}
    >
      <View style={styles.row}>
        <View style={[styles.icon, { backgroundColor: urgent ? colors.surface : colors.accentMuted }]}>
          <Ionicons name={urgent ? 'warning-outline' : 'time-outline'} size={20} color={urgent ? colors.error : colors.accent} />
        </View>
        <View style={styles.body}>
          <Text style={[styles.title, { color: urgent ? colors.error : colors.textPrimary }]} numberOfLines={2}>
            {s.summary}{luogo ? ` · ${luogo}` : ''}
          </Text>
          {iniziata ? <Text style={[styles.meta, { color: colors.textSecondary }]}>Iniziato alle {iniziata}</Text> : null}
        </View>
      </View>

      <Text style={[styles.big, { color: urgent ? colors.error : colors.textPrimary }]} testID={`${testID}-stima`}>{grande}</Text>
      {urgent && esito?.action_summary ? (
        <Text style={[styles.meta, { color: colors.textSecondary }]}>{esito.action_summary}</Text>
      ) : spiegazione ? (
        <Text style={[styles.meta, { color: colors.textTertiary }]}>{spiegazione}</Text>
      ) : null}

      {fatti.length ? (
        <View style={styles.facts} testID={`${testID}-condizioni`}>
          {fatti.map((f) => (
            <Text key={f} style={[styles.fact, { color: colors.textSecondary, backgroundColor: colors.backgroundPrimary }]}>{f}</Text>
          ))}
        </View>
      ) : null}

      {barra ? (
        <View style={styles.track} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
          <View style={[styles.bar, { backgroundColor: colors.divider }]} />
          <View style={[styles.fill, { width: pct(tNow), backgroundColor: colors.accent }]} />
          {Number.isFinite(tWin0) ? (
            <View style={[styles.win, {
              left: pct(tWin0),
              width: `${Math.max(2, (((Number.isFinite(tWin1) ? tWin1 : tWin0) - tWin0) / (fine - t0)) * 100)}%` as const,
              borderColor: colors.success, backgroundColor: colors.successBg,
            }]} />
          ) : null}
          {Number.isFinite(tCheck) ? (
            <View style={[styles.check, { left: pct(tCheck), borderColor: colors.accent, backgroundColor: colors.surface }]} />
          ) : null}
          <View style={[styles.now, { left: pct(tNow), backgroundColor: colors.textPrimary }]} />
        </View>
      ) : null}

      <View style={[styles.foot, { borderTopColor: colors.divider }]}>
        <Text style={[styles.footText, { color: colors.textTertiary }]}>
          {prossimo ? <>Prossimo controllo <Text style={{ color: colors.textSecondary, fontWeight: '700' }}>{prossimo}</Text></> : 'Prossimo controllo da fissare'}
        </Text>
        {prossimo ? <Text style={[styles.footText, { color: colors.textTertiary }]}>Ti avviso io</Text> : null}
      </View>

      {urgent ? (
        <View style={styles.actions}>
          <Pressable
            onPress={() => onOpen(a)}
            accessibilityRole="button"
            style={({ pressed }) => [styles.btn, { backgroundColor: colors.error }, pressed && styles.pressed]}
            testID={`${testID}-apri`}
          >
            <Text style={[styles.btnText, { color: colors.onAccent }]}>Apri</Text>
          </Pressable>
          {onDismiss ? (
            <Pressable
              onPress={() => void onDismiss(a)}
              accessibilityRole="button"
              style={({ pressed }) => [styles.btn, { backgroundColor: colors.surface }, pressed && styles.pressed]}
              testID={`${testID}-rimuovi`}
            >
              <Text style={[styles.btnText, { color: colors.textSecondary }]}>Ignora</Text>
            </Pressable>
          ) : null}
        </View>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  board: { gap: 4 },
  chips: { flexDirection: 'row', gap: 8, marginBottom: 4, flexWrap: 'wrap' },
  chip: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 7 },
  chipText: { fontSize: 13.5, fontWeight: '600' },
  chipCount: { fontWeight: '700' },
  section: { fontSize: 12, fontWeight: '700', letterSpacing: 1.1, marginTop: 14, marginBottom: 8, marginHorizontal: 4 },
  card: { borderWidth: 1, borderRadius: 20, padding: 14, marginBottom: 10, gap: 2 },
  pressed: { opacity: 0.8 },
  row: { flexDirection: 'row', gap: 12, alignItems: 'flex-start' },
  icon: { width: 40, height: 40, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  body: { flex: 1, gap: 2 },
  tagRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  tag: { fontSize: 12, fontWeight: '700', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, overflow: 'hidden' },
  ago: { fontSize: 12 },
  title: { fontSize: 16.5, lineHeight: 22, fontWeight: '600', letterSpacing: -0.25 },
  meta: { fontSize: 14, lineHeight: 20 },
  actions: { flexDirection: 'row', gap: 8, marginTop: 12, paddingLeft: 52, flexWrap: 'wrap' },
  btn: { borderRadius: 12, paddingHorizontal: 14, paddingVertical: 9 },
  btnText: { fontSize: 14.5, fontWeight: '600' },
  big: { fontSize: 21, lineHeight: 27, fontWeight: '700', letterSpacing: -0.4, marginTop: 10 },
  facts: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 10 },
  fact: { fontSize: 12.5, fontWeight: '600', paddingHorizontal: 9, paddingVertical: 5, borderRadius: 9, overflow: 'hidden' },
  track: { height: 24, marginTop: 12, position: 'relative' },
  bar: { position: 'absolute', top: 9, left: 0, right: 0, height: 6, borderRadius: 6 },
  fill: { position: 'absolute', top: 9, left: 0, height: 6, borderRadius: 6 },
  win: { position: 'absolute', top: 6, height: 12, borderRadius: 6, borderWidth: 1.5 },
  check: { position: 'absolute', top: 7, width: 10, height: 10, marginLeft: -5, borderRadius: 5, borderWidth: 2 },
  now: { position: 'absolute', top: 3, width: 3, height: 18, borderRadius: 2, marginLeft: -1.5 },
  foot: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 12, paddingTop: 11, borderTopWidth: 1 },
  footText: { fontSize: 13 },
  note: { fontSize: 12.5, textAlign: 'center', marginTop: 6, lineHeight: 18 },
});
