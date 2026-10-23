import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import type {
  HomeAgentWork,
  HomeInsight,
  HomeItem,
  HomeOpportunity,
  OpenQuestionItem,
  ProactiveSuggestion,
} from '@/src/api/client';
import { IconBubble, OraBadge, OraButton, OraCard, OraLink, SectionTitle } from '@/src/components/ora-ui';
import { ora, oraType } from '@/src/theme/oraSurface';
import { ContextualCardVisual } from './ContextualCardVisual';
import { agoLabel, relativeDayLabel } from './homeItemView';
import { aggiornamentoScaduto, elencoAggiornamenti, quandoAggiornamento, type Aggiornamento } from './aggiornamenti';
import { UpdatesBoard, sintesiAggiornamenti } from './UpdatesBoard';
import { SituationDetails, SituationOutcomeSummary } from '@/src/components/ora/SituationOutcomeSummary';

/* -------------------------------------------------------------------------- */
/* Shared section chrome                                                       */
/* -------------------------------------------------------------------------- */

export function SectionShell({
  title,
  icon,
  subtitle,
  linkLabel,
  onLink,
  count,
  footerLabel,
  onFooter,
  children,
  testID,
}: {
  title: string;
  /** L'icona accanto al titolo, come nella reference approvata. */
  icon?: any;
  subtitle?: string;
  /** «3 da rispondere ›» — porta dove stanno tutte. */
  linkLabel?: string;
  onLink?: () => void;
  count?: number;
  footerLabel?: string;
  onFooter?: () => void;
  children: React.ReactNode;
  testID?: string;
}) {
  return (
    <OraCard style={styles.section} testID={testID}>
      <SectionTitle
        icon={icon}
        title={title}
        subtitle={subtitle}
        right={linkLabel ? <OraLink label={linkLabel} onPress={onLink || onFooter} /> : undefined}
      />

      <View style={styles.sectionBody}>{children}</View>

      {footerLabel && onFooter && !linkLabel ? (
        <Pressable
          onPress={onFooter}
          style={({ pressed }) => [styles.footer, pressed && styles.pressed]}
          accessibilityRole="button"
        >
          <Text style={[styles.footerLabel, { color: ora.cta }]}>{footerLabel}</Text>
          <Ionicons name="arrow-forward" size={13} color={ora.cta} />
        </Pressable>
      ) : null}
    </OraCard>
  );
}

/* -------------------------------------------------------------------------- */
/* DOMANDE PER TE — ORA is waiting on an answer                                */
/* -------------------------------------------------------------------------- */

export function QuestionsSection({
  open = [],
  questions,
  busyId,
  onAnswer,
  onAnswerOpen,
  onAnswerInline,
  onSeeAll,
}: {
  /**
   * Questions ORA is actually blocked on.
   *
   * These come first because they are a different kind of thing from the rows
   * below them: answering one continues a piece of work that stopped, where a
   * suggestion is something ORA thought worth raising. Both belong under the
   * same heading — from the reader's side they are all "things ORA is waiting
   * to hear from me" — but the blockers are the ones with consequences.
   */
  open?: OpenQuestionItem[];
  questions: ProactiveSuggestion[];
  busyId?: string | null;
  onAnswer: (s: ProactiveSuggestion) => void;
  onAnswerOpen?: (q: OpenQuestionItem) => void;
  onAnswerInline?: (q: OpenQuestionItem, action: string) => void;
  onSeeAll?: () => void;
}) {
  const { colors } = useTheme();
  if (!questions.length && !open.length) return null;

  return (
    <SectionShell
      title="Domande per te"
      icon="chatbubble-ellipses-outline"
      subtitle="Ci sono alcune cose su cui ho bisogno della tua opinione."
      linkLabel={`${questions.length + open.length} da rispondere`}
      onLink={onSeeAll}
      footerLabel={onSeeAll ? 'Vedi tutte le domande' : undefined}
      onFooter={onSeeAll}
      testID="home-questions"
    >
      {open.slice(0, 3).map((q) => (
        <View key={q.id} style={styles.row}>
          <IconBubble name={iconForQuestion(q.context_label)} />
          <View style={styles.rowText}>
            <Text style={[styles.rowTitle, { color: colors.textPrimary }]} numberOfLines={3}>
              {q.question}
            </Text>
            {q.why_needed || q.context_label ? (
              <Text style={[styles.rowMeta, { color: colors.textTertiary }]} numberOfLines={2}>
                {q.why_needed || q.context_label}
              </Text>
            ) : null}
          </View>
          {/*
            Alcune domande hanno gia' la loro risposta addosso.

                UNA DOMANDA DA SI' O NO SI RISPONDE DOVE LA SI LEGGE.

            «L'affitto e' 760?» non ha bisogno di una conversazione: ha
            bisogno di un dito. Mandare la persona in chat per una parola
            sarebbe farle fare un viaggio per dire di si'. Le altre domande —
            quelle a cui serve davvero raccontare qualcosa — restano com'erano.
          */}
          {q.answers?.length ? (
            <View style={styles.rowAnswers}>
              {q.answers.map((a) => (
                <Pressable
                  key={a.action}
                  onPress={() => onAnswerInline?.(q, a.action)}
                  style={({ pressed }) => [
                    styles.rowCta,
                    { borderColor: colors.accent },
                    pressed && styles.pressed,
                  ]}
                  accessibilityRole="button"
                  accessibilityLabel={`${a.label}: ${q.question}`}
                  testID={`home-question-${a.action}`}
                >
                  <Text style={[styles.rowCtaLabel, { color: colors.accent }]}>
                    {a.label}
                  </Text>
                </Pressable>
              ))}
            </View>
          ) : (
          <OraButton
            label="Rispondi"
            kind="secondary"
            compact
            onPress={() => onAnswerOpen?.(q)}
            accessibilityLabel={`Rispondi: ${q.question}`}
            testID={`home-open-question-${q.id}`}
          />
          )}
        </View>
      ))}

      {questions.slice(0, 3).map((q) => (
        <View key={q.id} style={styles.row}>
          <IconBubble name={iconForQuestion(q.title)} />
          <View style={styles.rowText}>
            <Text style={[styles.rowTitle, { color: colors.textPrimary }]} numberOfLines={2}>
              {q.title}
            </Text>
            {/*
              Two lines, because one was not enough at 390px: with the answer
              button beside it this line had 166px to say "Proposta: mercoledì
              3 settembre alle 11:00", and a proposed date cut off before the
              time is worse than no date at all. The row is not pressable, so
              there is nowhere else to go and read it.
            */}
            {q.reason ? (
              <Text style={[styles.rowMeta, { color: colors.textTertiary }]} numberOfLines={2}>
                {q.reason}
              </Text>
            ) : null}
          </View>
          <OraButton
            label="Rispondi"
            kind="secondary"
            compact
            busy={busyId === q.id}
            onPress={() => onAnswer(q)}
            accessibilityLabel={`Rispondi: ${q.title}`}
            testID={`home-question-answer-${q.id}`}
          />
        </View>
      ))}
    </SectionShell>
  );
}

/* -------------------------------------------------------------------------- */
/* OGGI                                                                        */
/* -------------------------------------------------------------------------- */

export function TodaySection({
  items,
  onOpen,
  onSeeAll,
}: {
  items: HomeItem[];
  onOpen: (item: HomeItem) => void;
  onSeeAll?: () => void;
}) {
  const { colors } = useTheme();
  if (!items.length) return null;

  return (
    <SectionShell
      title="OGGI"
      footerLabel={onSeeAll ? 'Vedi agenda completa' : undefined}
      onFooter={onSeeAll}
      testID="home-today"
    >
      {items.slice(0, 4).map((item) => {
        const at = item.start_at || item.due_at;
        const time = at
          ? new Date(at).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })
          : null;
        return (
          <Pressable
            key={item.id}
            onPress={() => onOpen(item)}
            style={({ pressed }) => [styles.row, pressed && styles.pressed]}
            accessibilityRole="button"
            testID={`home-today-${item.id}`}
          >
            {time ? (
              <Text style={[styles.time, { color: colors.textSecondary }]}>{time}</Text>
            ) : (
              <View style={styles.timeSpacer} />
            )}
            <ContextualCardVisual
              item={item}
              imageSource={item.visual?.status === 'ready' ? item.visual.url : null}
              generating={item.visual?.status === 'queued' || item.visual?.status === 'generating'}
              size="row"
              style={styles.rowVisual}
            />
            <View style={styles.rowText}>
              <Text style={[styles.rowTitle, { color: colors.textPrimary }]} numberOfLines={1}>
                {item.title}
              </Text>
              {item.location || item.subtitle ? (
                <Text style={[styles.rowMeta, { color: colors.textTertiary }]} numberOfLines={1}>
                  {item.location || item.subtitle}
                </Text>
              ) : null}
            </View>
          </Pressable>
        );
      })}
    </SectionShell>
  );
}

/* -------------------------------------------------------------------------- */
/* AGGIORNAMENTI DI ORA                                                        */
/* -------------------------------------------------------------------------- */

export function UpdatesFeed({
  suggestions,
  insights,
  opportunities,
  agentWork,
  busyId,
  onOpen,
  onDismiss,
  onInsight,
  onOpportunityOpen,
  onOpportunityDismiss,
  onOpportunityDefer,
  onSeeAll,
  onOpenWork,
}: {
  suggestions: ProactiveSuggestion[];
  insights: HomeInsight[];
  /** What ORA judged worth saying, and worth saying now. Usually none. */
  opportunities?: HomeOpportunity[];
  /** Outcomes ORA is pursuing on their behalf. Usually none. */
  agentWork?: HomeAgentWork[];
  busyId?: string | null;
  onOpen: (s: ProactiveSuggestion) => void;
  onDismiss: (id: string) => void;
  onInsight: (i: HomeInsight) => void;
  onOpportunityOpen?: (o: HomeOpportunity) => void;
  onOpportunityDismiss?: (o: HomeOpportunity) => void;
  onOpportunityDefer?: (o: HomeOpportunity) => void;
  onSeeAll?: () => void;
  /** Dove si apre il dettaglio di un lavoro dell'agente. */
  onOpenWork?: (id: string) => void;
}) {
  const { colors } = useTheme();
  /*
    The backend already decided which of these belong here and how many —
    two judgements, both the model's. Slicing again is not a second opinion,
    it is the last line of defence: whatever arrives, this section stays a
    section and never becomes a list.
  */
  const raised = (opportunities || []).filter(o => !aggiornamentoScaduto(o.valid_until)).slice(0, 2);
  /*
    Outcomes, not workflow. Two at most, like everything else here: a person
    wanting to know whether something is handled does not want a project
    board, and ORA doing five things at once is a different problem.
  */
  const working = (agentWork || []).filter(w => !aggiornamentoScaduto(w.valid_until)).slice(0, 2);
  const visibleSuggestions = suggestions.filter(s => !aggiornamentoScaduto(s.expires_at)).slice(0, 3);
  const visibleInsights = insights.filter(i => !aggiornamentoScaduto(i.valid_until)).slice(0, 3);
  const total = visibleSuggestions.length + visibleInsights.length + raised.length + working.length;
  if (!total) return null;

  /*
    Bacheca approvata il 23/10/2026: Adesso → Serve te → ORA ci sta pensando.
    Lo stesso elenco della pagina (elencoAggiornamenti), costruito dalle liste
    già filtrate qui sopra, così numero e contenuto non si scollano.
  */
  const righe = elencoAggiornamenti({
    agent_work: working,
    opportunities: raised,
    ora_ti_consiglia: visibleSuggestions,
    insights: visibleInsights,
  } as Parameters<typeof elencoAggiornamenti>[0]);
  const apri = (a: Aggiornamento) => {
    if (a.genere === 'lavoro') return onOpenWork ? onOpenWork(a.id) : onSeeAll?.();
    if (a.genere === 'occasione') {
      const o = raised.find((x) => x.id === a.id);
      return o && onOpportunityOpen ? onOpportunityOpen(o) : onSeeAll?.();
    }
    if (a.genere === 'suggerimento') {
      const sug = visibleSuggestions.find((x) => x.id === a.id);
      return sug ? onOpen(sug) : onSeeAll?.();
    }
    const ins = visibleInsights.find((x) => x.id === a.id);
    return ins ? onInsight(ins) : onSeeAll?.();
  };
  const rimuovi = (a: Aggiornamento) => {
    if (a.genere === 'occasione') {
      const o = raised.find((x) => x.id === a.id);
      if (o) onOpportunityDismiss?.(o);
      return;
    }
    if (a.genere === 'suggerimento') onDismiss(a.id);
  };
  const testId = (a: Aggiornamento) =>
    a.genere === 'suggerimento' ? `home-update-${a.id}`
      : a.genere === 'occasione' ? `home-opportunity-${a.id}`
        : a.genere === 'spunto' ? `home-insight-${a.id}`
          : `home-work-${a.id}`;

  return (
    <SectionShell
      title="Aggiornamenti di ORA"
      icon="sparkles-outline"
      subtitle={sintesiAggiornamenti(righe) || 'Ecco cosa sta succedendo, in modo chiaro.'}
      linkLabel={total === 1 ? '1 aggiornamento' : `${total} aggiornamenti`}
      onLink={onSeeAll}
      footerLabel={onSeeAll ? 'Vedi tutti gli aggiornamenti' : undefined}
      onFooter={onSeeAll}
      testID="home-updates"
    >
      <UpdatesBoard
        righe={righe}
        onOpen={apri}
        onDismiss={rimuovi}
        canDismiss={(a) =>
          (a.genere === 'occasione' && !!onOpportunityDismiss) || (a.genere === 'suggerimento' && busyId !== a.id)}
        testIdFor={testId}
        limit={4}
        showFilters={false}
        showNote={false}
      />
    </SectionShell>
  );
}

/* -------------------------------------------------------------------------- */
/* PIÙ AVANTI                                                                  */
/* -------------------------------------------------------------------------- */

export function HorizonSection({
  items,
  onOpen,
  onSeeAll,
}: {
  items: HomeItem[];
  onOpen: (item: HomeItem) => void;
  onSeeAll?: () => void;
}) {
  const { colors } = useTheme();
  if (!items.length) return null;

  return (
    <SectionShell
      title="PIÙ AVANTI"
      footerLabel={onSeeAll ? 'Vedi tutto il calendario' : undefined}
      onFooter={onSeeAll}
      testID="home-horizon"
    >
      {items.slice(0, 4).map((item) => {
        const at = item.start_at || item.due_at || item.goal_target_date;
        const rel = relativeDayLabel(at);
        const d = at ? new Date(at) : null;
        return (
          <Pressable
            key={item.id}
            onPress={() => onOpen(item)}
            style={({ pressed }) => [styles.row, pressed && styles.pressed]}
            accessibilityRole="button"
            testID={`home-horizon-${item.id}`}
          >
            {d ? (
              <View style={styles.dateChip}>
                <Text style={[styles.dateDay, { color: colors.textPrimary }]}>{d.getDate()}</Text>
                <Text style={[styles.dateMonth, { color: colors.textTertiary }]}>
                  {d.toLocaleDateString('it-IT', { month: 'short' }).replace('.', '').toUpperCase()}
                </Text>
              </View>
            ) : (
              <View style={styles.timeSpacer} />
            )}
            <ContextualCardVisual
              item={item}
              imageSource={item.visual?.status === 'ready' ? item.visual.url : null}
              generating={item.visual?.status === 'queued' || item.visual?.status === 'generating'}
              size="row"
              style={styles.rowVisual}
            />
            <View style={styles.rowText}>
              <Text style={[styles.rowTitle, { color: colors.textPrimary }]} numberOfLines={1}>
                {item.title}
              </Text>
              {item.subtitle || item.description ? (
                <Text style={[styles.rowMeta, { color: colors.textTertiary }]} numberOfLines={1}>
                  {item.subtitle || item.description}
                </Text>
              ) : null}
            </View>
            {rel ? (
              <View style={[styles.relChip, { backgroundColor: colors.warningBg }]}>
                <Text style={[styles.relText, { color: colors.warning }]}>{rel}</Text>
              </View>
            ) : null}
          </Pressable>
        );
      })}
    </SectionShell>
  );
}

/* -------------------------------------------------------------------------- */

const styles = StyleSheet.create({
  section: { gap: 18 },
  updateRow: { flexDirection: 'row', gap: 14, alignItems: 'flex-start' },
  updateBody: { flex: 1, gap: 4 },
  updateHead: { flexDirection: 'row', alignItems: 'center', gap: 10, flexWrap: 'wrap' },
  updateActions: { flexDirection: 'row', gap: 10, marginTop: 10, flexWrap: 'wrap' },
  sectionHead: { flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.sm },
  sectionTitle: {
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 1.3,
    flex: 1,
  },
  badge: {
    minWidth: 22,
    height: 22,
    borderRadius: 11,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 6,
  },
  badgeText: { fontSize: 12, fontWeight: '700' },
  sectionBody: { gap: 18 },
  /*
    On a phone this row kept its horizontal shape and left the words about
    165px to live in, so a two-line clamp cut the question itself in half with
    no pressable row to open and read the rest. Wrapping lets the action drop
    beneath the text once the text needs the width; on a wide screen nothing
    moves, because nothing has to.
  */
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: tokens.spacing.md,
    minHeight: 48,
    flexWrap: 'wrap',
  },
  rowVisual: { width: 34, height: 34 },
  rowText: { flex: 1, gap: 2, minWidth: 190 },
  rowTitle: { fontSize: 14, fontWeight: '500', lineHeight: 20 },
  rowMeta: { fontSize: 12, lineHeight: 17 },
  /*
    Hit area, not weight. These three sat at 34, 24 and 32 pixels tall — under
    the floor on a phone, and the dismiss cross was the smallest control in the
    product. The label, the border and the spacing are untouched; only the box
    a thumb has to find grew.
  */
  rowAnswers: { flexDirection: 'row', gap: 8 },
  rowCta: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.md,
    paddingHorizontal: tokens.spacing.md,
    minHeight: tokens.touch.min,
    justifyContent: 'center',
  },
  rowCtaLabel: { fontSize: 13, fontWeight: '600' },
  time: { fontSize: 13, fontWeight: '500', width: 46 },
  timeSpacer: { width: 46 },
  dateChip: { width: 46, alignItems: 'flex-start' },
  dateDay: { fontSize: 17, fontWeight: '700', lineHeight: 20 },
  dateMonth: { fontSize: 10, fontWeight: '600', letterSpacing: 0.5 },
  relChip: {
    borderRadius: tokens.radius.sm,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  relText: { fontSize: 11, fontWeight: '600' },
  ago: { fontSize: 11, marginLeft: 'auto', paddingLeft: 6 },
  dismiss: {
    width: tokens.touch.min, height: tokens.touch.min,
    alignItems: 'center', justifyContent: 'center', marginRight: -10,
  },
  footer: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    minHeight: tokens.touch.min, alignSelf: 'flex-start',
  },
  footerLabel: { fontSize: 13, fontWeight: '600' },
  pressed: { opacity: 0.65 },
  disabled: { opacity: 0.5 },

  /*
    An opportunity is a sentence, not a row. The other entries here are things
    that already happened and read fine at a glance; this one is ORA saying
    something and offering to talk about it, so it gets room to be read and
    three plain answers underneath. No badge, no colour coding, no icon
    competing for the eye — quiet is the point.
  */
  oppItem: {
    paddingVertical: tokens.spacing.md,
    gap: 4,
  },
  oppTitle: {
    fontSize: tokens.typography.body.fontSize,
    lineHeight: 21,
    fontWeight: '500',
    letterSpacing: -0.15,
  },
  oppWhy: {
    fontSize: tokens.typography.bodySmall.fontSize,
    lineHeight: tokens.typography.bodySmall.lineHeight,
  },
  oppOffer: {
    fontSize: tokens.typography.bodySmall.fontSize,
    lineHeight: tokens.typography.bodySmall.lineHeight,
    marginTop: 2,
  },
  oppActions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: 14,
    marginTop: 6,
  },
  oppCta: {
    minHeight: tokens.touch.min,
    justifyContent: 'center',
  },
  oppCtaText: { fontSize: 13, fontWeight: '600' },
});


/* -------------------------------------------------------------------------- */
/* Un aggiornamento, con la sua provenienza                                    */
/* -------------------------------------------------------------------------- */

/**
 * Che cosa, da dove, perché conta, a che punto è, e cosa serve a te.
 *
 * V3.21.3: prima diceva soltanto «Avere il ritiro del certificato in agenda per
 * giovedì. Sto controllando come stanno le cose.» — una frase che non dice da
 * dove nasce né se serva fare qualcosa. Niente di quello che c'è qui è
 * inventato: se una parte non arriva dal backend, non compare.
 */
export function AgentWorkRow({
  work,
  onOpen,
}: {
  work: HomeAgentWork;
  onOpen?: () => void;
}) {
  const situation = work.situation;
  if (situation) {
    return (
      <View style={styles.updateRow} testID={`home-agent-${work.id}`}>
        <IconBubble name="time-outline" />
        <View style={styles.updateBody}>
          <Text style={[oraType.body, { color: ora.ink, fontWeight: '600' }]}>{situation.summary}</Text>
          <SituationOutcomeSummary compact
            outcome={situation.outcome}
            desiredOutcome={situation.desired_outcome}
            situationRevision={situation.revision}
            followupStatus={situation.followup_status}
            testID={`home-situation-outcome-${work.id}`}
          />
          {work.needs_you ? <Text style={[oraType.body, { color: ora.attention }]}>
            Domanda per te: {work.needs_you}
          </Text> : null}
          {work.problem ? <Text style={[oraType.small, { color: ora.attention }]}>{work.problem}</Text> : null}
          <SituationDetails>
            <Text style={[oraType.small, { color: ora.ink3 }]}>Fonte: {work.source || 'originale non disponibile'}</Text>
            {situation.created_at ? <Text style={[oraType.small, { color: ora.ink3 }]}>
              Registrata: {quandoAggiornamento(situation.created_at)}
            </Text> : null}
            {situation.monitor_diagnosis ? <Text style={[oraType.small, { color: ora.ink2 }]}>
              {situation.monitor_diagnosis}
            </Text> : null}
            {situation.next_check_label ? <Text style={[oraType.small, { color: ora.ink2 }]}>
              Prossimo controllo: {situation.next_check_label}
            </Text> : null}
            {situation.last_checked_at ? <Text style={[oraType.small, { color: ora.ink2 }]}>
              Ultima verifica: {quandoAggiornamento(situation.last_checked_at)}
            </Text> : null}
            {situation.last_result ? <Text style={[oraType.small, { color: ora.ink2 }]}>{situation.last_result}</Text> : null}
          </SituationDetails>
          {onOpen ? <View style={styles.updateActions}>
            <OraButton label="Apri dettagli" kind="secondary" compact onPress={onOpen}
              testID={`home-agent-${work.id}-apri`} />
          </View> : null}
        </View>
      </View>
    );
  }
  return (
    <View style={styles.updateRow} testID={`home-agent-${work.id}`}>
      <IconBubble name="document-text-outline" />
      <View style={styles.updateBody}>
        <View style={styles.updateHead}>
          <Text style={[oraType.body, { color: ora.ink, fontWeight: '600', flexShrink: 1 }]}>
            {work.what}
          </Text>
          <OraBadge
            label={
              work.needs_you
                ? 'Serve una risposta'
                : work.problem
                  ? 'Richiede attenzione'
                  : work.has_real_activity
                    ? 'ORA si è mossa'
                    : 'In attesa'
            }
            tone={work.needs_you || work.problem ? 'attention' : 'info'}
          />
        </View>
        {/*
          La fonte, detta per intero. Quando l'originale non è ricostruibile la
          card lo dichiara invece di riempire la riga con una perifrasi.
        */}
        <Text style={[oraType.small, { color: ora.ink3 }]} numberOfLines={2}>
          Fonte: {work.source || 'originale non disponibile'}
        </Text>
        {work.unknown ? (
          <Text style={[oraType.small, { color: ora.attention }]} numberOfLines={2}>
            {work.unknown}
          </Text>
        ) : null}
        {work.detected || work.why_now ? (
          <Text style={[oraType.small, { color: ora.ink2 }]} numberOfLines={3}>
            <Text style={{ fontWeight: '700' }}>Perché conta: </Text>
            {work.detected || work.why_now}
          </Text>
        ) : null}
        {work.already_done ? (
          <Text style={[oraType.small, { color: ora.ink2 }]} numberOfLines={3}>
            <Text style={{ fontWeight: '700' }}>Ho già fatto: </Text>
            {work.already_done}
          </Text>
        ) : (
          <Text style={[oraType.small, { color: ora.ink2 }]} numberOfLines={2}>
            {work.state}
          </Text>
        )}
        {work.next_step || work.needs_you ? (
          <Text
            style={[
              oraType.small,
              { color: work.needs_you ? ora.attention : ora.ink2 },
            ]}
            numberOfLines={3}
          >
            <Text style={{ fontWeight: '700' }}>Prossimo passo: </Text>
            {work.next_step || work.needs_you}
          </Text>
        ) : null}
        {/*
          Nessun bottone morto: se non c'è dove aprire, il bottone non c'è.
        */}
        {onOpen ? (
          <View style={styles.updateActions}>
            <OraButton
              label="Apri dettagli"
              kind="secondary"
              compact
              onPress={onOpen}
              testID={`home-agent-${work.id}-apri`}
            />
          </View>
        ) : null}
      </View>
    </View>
  );
}

/** L'icona di una domanda, dal contesto che la accompagna. */
export function iconForQuestion(label?: string | null): any {
  const t = (label || '').toLowerCase();
  if (t.includes('chiamat') || t.includes('numero') || t.includes('telefon')) return 'call-outline';
  if (t.includes('viagg') || t.includes('volo') || t.includes('treno')) return 'airplane-outline';
  if (t.includes('fattur') || t.includes('document') || t.includes('intestaz')) return 'document-text-outline';
  if (t.includes('calendar') || t.includes('appuntament')) return 'calendar-outline';
  return 'chatbubble-ellipses-outline';
}
