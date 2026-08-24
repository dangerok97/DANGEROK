/**
 * Dynamic document utility panels by macro-category (Documents V2).
 * Empty sections are omitted.
 */
import React from 'react';
import { View, Text, TextInput, Linking } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { tokens } from '@/src/theme/tokens';
import { ActionBtn } from '@/src/components/ui/ActionBtn';
import {
  AdminAnalysis,
  DocumentAnalysisResponse,
  DocumentInsights,
  DocumentItem,
  EducationAnalysis,
  EventCandidate,
  Flashcard,
  QuizSession,
} from '@/src/api/client';

function FieldRow({ k, v }: { k: string; v?: string | null }) {
  if (v == null || String(v).trim() === '') return null;
  return (
    <View style={{ marginBottom: 8 }}>
      <Text style={{ color: tokens.color.onSurfaceMuted, fontSize: 11, marginBottom: 2 }}>{k}</Text>
      <Text style={{ color: tokens.color.onSurface, fontSize: 14, lineHeight: 20 }}>{v}</Text>
    </View>
  );
}

function Card({
  title, icon, children,
}: { title: string; icon?: keyof typeof Ionicons.glyphMap; children: React.ReactNode }) {
  return (
    <View style={{
      backgroundColor: tokens.color.surfaceSecondary, borderRadius: 14, padding: 14,
      borderWidth: 1, borderColor: tokens.color.border, gap: 4,
    }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        {icon ? <Ionicons name={icon} size={16} color={tokens.color.onSurface} /> : null}
        <Text style={{ color: tokens.color.onSurface, fontWeight: '600', fontSize: 15 }}>{title}</Text>
      </View>
      {children}
    </View>
  );
}

function fmt(iso?: string | null) {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleString('it-IT', {
      day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}

export type UtilityHandlers = {
  busy: string | null;
  onConfirmEvent: (ev: EventCandidate, sync?: boolean) => void;
  onDismissEvent: (ev: EventCandidate) => void;
  onRemindEvent: (ev: EventCandidate) => void;
  onReanalyze: () => void;
  onStudy: (action: string) => void;
  onQuizAnswer: () => void;
  onAdminComplete: (index: number) => void;
  onAdminDeadline: (syncGoogle: boolean) => void;
  onPatchFields?: (body: {
    user_title?: string;
    admin_analysis?: Record<string, unknown>;
  }) => void;
  askQ: string;
  setAskQ: (v: string) => void;
  askA: string | null;
  onAsk: () => void;
  quizAnswer: string;
  setQuizAnswer: (v: string) => void;
  flashOpen: Record<string, boolean>;
  setFlashOpen: (v: Record<string, boolean> | ((p: Record<string, boolean>) => Record<string, boolean>)) => void;
};

export function DocumentUtilityPanel({
  doc, ins, analysis, h,
}: {
  doc: DocumentItem;
  ins: DocumentInsights;
  analysis: DocumentAnalysisResponse | null;
  h: UtilityHandlers;
}) {
  const a = analysis?.analysis;
  const macro = a?.macro_category || 'generic';
  const events = (analysis?.event_candidates || []).filter(
    (e) => e.status === 'proposed' || e.status === 'remind_later' || e.status === 'confirmed',
  );
  const edu = analysis?.education_analysis as EducationAnalysis | null | undefined;
  const admin = analysis?.admin_analysis as AdminAnalysis | null | undefined;
  const flashcards = analysis?.flashcards || [];
  const quiz = analysis?.quiz_session as QuizSession | null | undefined;
  const actions = analysis?.generic_actions || [];
  const isEvent = macro === 'event' || macro === 'travel' || events.length > 0;
  const isStudy = macro === 'education' || !!edu;
  const isAdmin = ['administrative', 'financial', 'receipt', 'contract', 'legal'].includes(macro) || !!admin;
  const isMedical = macro === 'medical';

  return (
    <View style={{ gap: 12 }}>
      <Card title="Elaborazione" icon="pulse-outline">
        <FieldRow k="Stato" v={analysis?.pipeline_status_label} />
        <FieldRow k="Errore" v={analysis?.pipeline_error} />
        <FieldRow k="Modalità" v={a?.ai_used ? 'Arricchita con AI' : a?.local_only ? 'Analisi locale' : null} />
        <View style={{ marginTop: 8 }}>
          <ActionBtn icon="refresh" label="Riesegui analisi" onPress={h.onReanalyze} loading={h.busy === 'reanalyze'} />
        </View>
      </Card>

      <Card title={analysis?.display_title || a?.suggested_title || doc.filename} icon="document-text-outline">
        <FieldRow k="Categoria" v={a?.macro_category} />
        <FieldRow k="Sottotipo" v={a?.subcategory} />
        {/*
          PX1.1 — the "Affidabilità NN%" row is gone. It was a raw confidence
          score presented as a fact about the user's own document: a number
          they cannot evaluate, quietly asking them to decide how much of ORA's
          reading to believe. The panel already states the human state above
          (Stato, Modalità), and anything ORA is unsure about surfaces as
          something to confirm, not as a percentage.
        */}
        <FieldRow k="File originale" v={doc.original_filename || doc.filename} />
        <FieldRow k="Riepilogo" v={a?.summary} />
      </Card>

      {(isEvent || isMedical) && events.map((ev) => (
        <EventPanel key={ev.id} ev={ev} medical={isMedical} h={h} />
      ))}

      {isStudy && edu ? <StudyPanel edu={edu} flashcards={flashcards} quiz={quiz} h={h} /> : null}

      {isAdmin && (admin || actions.length) ? (
        <AdminPanel admin={admin} actions={actions} h={h} />
      ) : null}

      {!isEvent && !isStudy && !isAdmin ? (
        <GenericPanel a={a} ins={ins} />
      ) : null}

      <Card title="Chiedi al documento" icon="chatbubble-ellipses-outline">
        <TextInput
          value={h.askQ}
          onChangeText={h.setAskQ}
          placeholder="Domanda sul contenuto…"
          placeholderTextColor={tokens.color.onSurfaceMuted}
          style={{
            borderWidth: 1, borderColor: tokens.color.border, borderRadius: 10,
            padding: 10, color: tokens.color.onSurface, marginBottom: 8,
          }}
        />
        <ActionBtn primary icon="send" label="Chiedi" onPress={h.onAsk} loading={h.busy === 'ask'} />
        {h.askA ? (
          <Text style={{ marginTop: 8, color: tokens.color.onSurface, fontSize: 13, lineHeight: 18 }}>{h.askA}</Text>
        ) : null}
      </Card>
    </View>
  );
}

function EventPanel({
  ev, medical, h,
}: { ev: EventCandidate; medical: boolean; h: UtilityHandlers }) {
  return (
    <Card title={medical ? 'Appuntamento sanitario' : 'Evento / appuntamento'} icon="calendar-outline">
      {medical ? (
        <Text style={{ color: tokens.color.onSurfaceMuted, fontSize: 12, marginBottom: 8 }}>
          Solo dati di appuntamento presenti nel documento. Nessuna diagnosi, terapia o interpretazione clinica generata.
        </Text>
      ) : null}
      <FieldRow k="Titolo" v={medical ? 'Visita specialistica (titolo discreto su Google)' : ev.title} />
      <FieldRow k="Inizio" v={fmt(ev.start_datetime) || 'Da confermare'} />
      <FieldRow k="Fine" v={fmt(ev.end_datetime)} />
      <FieldRow k="Timezone" v={(ev as any).timezone || 'Europe/Rome'} />
      <FieldRow k="Luogo" v={ev.venue_name} />
      <FieldRow k="Indirizzo" v={[ev.address, ev.city].filter(Boolean).join(', ') || null} />
      <FieldRow k="Codice prenotazione" v={ev.booking_reference} />
      <FieldRow k="Priorità" v={ev.priority} />
      <FieldRow k="Urgenza" v={ev.urgency} />
      {ev.ambiguous_date ? <FieldRow k="Attenzione" v="Data ambigua — conferma richiesta" /> : null}
      {ev.missing_fields?.length ? <FieldRow k="Campi incerti" v={ev.missing_fields.join(', ')} /> : null}
      <FieldRow k="Stato" v={ev.status} />
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 }}>
        {(ev.status === 'proposed' || ev.status === 'remind_later') ? (
          <>
            <ActionBtn primary icon="checkmark" label="Salva solo in ORA" onPress={() => h.onConfirmEvent(ev, false)} loading={h.busy === `ev-${ev.id}`} />
            <ActionBtn primary icon="logo-google" label="ORA + Google Calendar" onPress={() => h.onConfirmEvent(ev, true)} loading={h.busy === `ev-${ev.id}-g`} />
            <ActionBtn icon="close" label="Non aggiungere" onPress={() => h.onDismissEvent(ev)} />
            <ActionBtn icon="time-outline" label="Più tardi" onPress={() => h.onRemindEvent(ev)} />
          </>
        ) : (
          <Text style={{ color: tokens.color.onSurfaceMuted, fontSize: 13 }}>Gestito ({ev.status})</Text>
        )}
        {ev.maps_url ? <ActionBtn icon="map-outline" label="Google Maps" onPress={() => Linking.openURL(ev.maps_url!)} /> : null}
        {ev.directions_url ? <ActionBtn icon="navigate-outline" label="Indicazioni" onPress={() => Linking.openURL(ev.directions_url!)} /> : null}
      </View>
    </Card>
  );
}

function StudyPanel({
  edu, flashcards, quiz, h,
}: {
  edu: EducationAnalysis;
  flashcards: Flashcard[];
  quiz?: QuizSession | null;
  h: UtilityHandlers;
}) {
  const turn = quiz?.turns?.[quiz.current_index];
  return (
    <>
      <Card title="Materiale di studio" icon="school-outline">
        <FieldRow k="Materia" v={edu.subject} />
        <FieldRow k="Argomento" v={edu.topic} />
        <FieldRow k="Livello" v={edu.level || edu.difficulty} />
        <FieldRow k="Titolo intelligente" v={edu.suggested_title} />
        <FieldRow k="Spiegazione semplice" v={edu.simple_explanation} />
        <FieldRow k="Riassunto breve" v={edu.summary_short} />
        <FieldRow k="Riassunto dettagliato" v={edu.summary_detailed} />
        {edu.outline?.length ? <FieldRow k="Schema" v={edu.outline.map((x) => `• ${x}`).join('\n')} /> : null}
        {edu.key_concepts?.length ? <FieldRow k="Concetti chiave" v={edu.key_concepts.join(' · ')} /> : null}
        {edu.definitions?.length ? <FieldRow k="Definizioni" v={edu.definitions.join('\n')} /> : null}
        {edu.important_people?.length ? <FieldRow k="Persone importanti" v={edu.important_people.join(', ')} /> : null}
        {edu.important_dates?.length ? <FieldRow k="Date importanti" v={edu.important_dates.join(', ')} /> : null}
        {edu.formulas?.length ? <FieldRow k="Formule" v={edu.formulas.join('\n')} /> : null}
        {edu.examples?.length ? <FieldRow k="Esempi" v={edu.examples.join('\n')} /> : null}
        {edu.questions_for_review?.length ? <FieldRow k="Domande di ripasso" v={edu.questions_for_review.join('\n')} /> : null}
        {edu.exam_questions?.length ? <FieldRow k="Possibili domande d'esame" v={edu.exam_questions.join('\n')} /> : null}
        <FieldRow k="Tempo lettura stimato" v={edu.estimated_read_minutes != null ? `${edu.estimated_read_minutes} min` : null} />
      </Card>
      <Card title="Strumenti di studio" icon="sparkles-outline">
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          <ActionBtn icon="chatbubble" label="Spiegamelo semplice" onPress={() => h.onStudy('explain_simple')} loading={h.busy === 'study-explain_simple'} />
          <ActionBtn icon="document-text" label="Riassunto breve" onPress={() => h.onStudy('summary_short')} loading={h.busy === 'study-summary_short'} />
          <ActionBtn icon="reader" label="Riassunto dettagliato" onPress={() => h.onStudy('summary_detailed')} loading={h.busy === 'study-summary_detailed'} />
          <ActionBtn icon="list" label="Crea schema" onPress={() => h.onStudy('outline')} loading={h.busy === 'study-outline'} />
          <ActionBtn icon="help-circle" label="Domande ripasso" onPress={() => h.onStudy('questions')} loading={h.busy === 'study-questions'} />
          <ActionBtn icon="school" label="Domande esame" onPress={() => h.onStudy('exam_questions')} loading={h.busy === 'study-exam_questions'} />
          <ActionBtn primary icon="albums" label="Genera flashcard" onPress={() => h.onStudy('flashcards')} loading={h.busy === 'study-flashcards'} />
          <ActionBtn primary icon="mic" label="Interrogami" onPress={() => h.onStudy('quiz_start')} loading={h.busy === 'study-quiz_start'} />
        </View>
      </Card>
      {flashcards.length ? (
        <Card title={`Flashcard (${flashcards.length})`} icon="albums-outline">
          {flashcards.map((fc) => (
            <View key={fc.id} style={{ marginBottom: 10 }}>
              <ActionBtn
                icon={h.flashOpen[fc.id] ? 'eye-off' : 'eye'}
                label={fc.question}
                onPress={() => h.setFlashOpen((p) => ({ ...p, [fc.id]: !p[fc.id] }))}
              />
              {h.flashOpen[fc.id] ? (
                <>
                  <Text style={{ color: tokens.color.onSurface, marginTop: 6, fontSize: 13 }}>{fc.answer}</Text>
                  <FieldRow k="Riferimento" v={fc.source_ref} />
                  <FieldRow k="Difficoltà" v={fc.difficulty} />
                  <FieldRow k="Stato ripasso" v={fc.review_status} />
                </>
              ) : null}
            </View>
          ))}
        </Card>
      ) : null}
      {quiz && quiz.status === 'active' && turn ? (
        <Card title="Interrogami" icon="mic-outline">
          <FieldRow k="Domanda" v={turn.question} />
          {quiz.turns.filter((t) => t.feedback).slice(-1).map((t, i) => (
            <FieldRow key={i} k="Feedback precedente" v={t.feedback} />
          ))}
          <TextInput
            value={h.quizAnswer}
            onChangeText={h.setQuizAnswer}
            placeholder="La tua risposta…"
            placeholderTextColor={tokens.color.onSurfaceMuted}
            style={{
              borderWidth: 1, borderColor: tokens.color.border, borderRadius: 10,
              padding: 10, color: tokens.color.onSurface, marginVertical: 8,
            }}
          />
          <ActionBtn primary icon="send" label="Invia risposta" onPress={h.onQuizAnswer} loading={h.busy === 'quiz'} />
        </Card>
      ) : null}
      {quiz && quiz.status === 'completed' ? (
        <Card title="Interrogazione completata" icon="checkmark-circle">
          {quiz.turns.map((t, i) => (
            <View key={i} style={{ marginBottom: 8 }}>
              <FieldRow k={`Q${i + 1}`} v={t.question} />
              <FieldRow k="Tua risposta" v={t.user_answer} />
              <FieldRow k="Feedback" v={t.feedback} />
            </View>
          ))}
        </Card>
      ) : null}
    </>
  );
}

function AdminPanel({
  admin, actions, h,
}: {
  admin?: AdminAnalysis | null;
  actions: Array<{ title: string; description?: string; due_datetime?: string | null; amount?: string | null; completed?: boolean }>;
  h: UtilityHandlers;
}) {
  const [editSubject, setEditSubject] = React.useState(admin?.subject || '');
  const [editAmount, setEditAmount] = React.useState(admin?.amount || '');
  const [editDue, setEditDue] = React.useState(admin?.due_date || '');
  React.useEffect(() => {
    setEditSubject(admin?.subject || '');
    setEditAmount(admin?.amount || '');
    setEditDue(admin?.due_date || '');
  }, [admin?.subject, admin?.amount, admin?.due_date]);

  return (
    <Card title="Amministrativo / finanziario" icon="receipt-outline">
      <Text style={{ color: tokens.color.onSurfaceMuted, fontSize: 12, marginBottom: 8 }}>
        Informazioni estratte dal documento — non costituisce consulenza professionale.
      </Text>
      {admin ? (
        <>
          <FieldRow k="Mittente" v={admin.sender} />
          <FieldRow k="Destinatario" v={admin.recipient} />
          <FieldRow k="Numero documento" v={admin.document_number} />
          <FieldRow k="Data" v={admin.issue_date} />
          <FieldRow k="Pagamento" v={admin.payment_method} />
          <FieldRow k="Spiegazione" v={admin.simple_explanation} />
          <FieldRow k="Priorità" v={admin.priority} />
          <FieldRow k="Urgenza" v={admin.urgency} />
          <FieldRow k="Stato" v={admin.completed ? 'Completato' : 'Da gestire'} />
          <Text style={{ color: tokens.color.onSurfaceMuted, fontSize: 11, marginTop: 8 }}>Correggi campi estratti</Text>
          <TextInput
            value={editSubject}
            onChangeText={setEditSubject}
            placeholder="Oggetto"
            placeholderTextColor={tokens.color.onSurfaceMuted}
            style={{
              borderWidth: 1, borderColor: tokens.color.border, borderRadius: 10,
              padding: 10, color: tokens.color.onSurface, marginTop: 6,
            }}
          />
          <TextInput
            value={editAmount}
            onChangeText={setEditAmount}
            placeholder="Importo"
            placeholderTextColor={tokens.color.onSurfaceMuted}
            style={{
              borderWidth: 1, borderColor: tokens.color.border, borderRadius: 10,
              padding: 10, color: tokens.color.onSurface, marginTop: 6,
            }}
          />
          <TextInput
            value={editDue}
            onChangeText={setEditDue}
            placeholder="Scadenza"
            placeholderTextColor={tokens.color.onSurfaceMuted}
            style={{
              borderWidth: 1, borderColor: tokens.color.border, borderRadius: 10,
              padding: 10, color: tokens.color.onSurface, marginTop: 6, marginBottom: 8,
            }}
          />
          {h.onPatchFields ? (
            <ActionBtn
              icon="save-outline"
              label="Salva correzioni"
              loading={h.busy === 'patch'}
              onPress={() => h.onPatchFields?.({
                admin_analysis: {
                  subject: editSubject,
                  amount: editAmount,
                  due_date: editDue,
                },
              })}
            />
          ) : null}
        </>
      ) : null}
      {actions.map((act, i) => (
        <View key={i} style={{ marginTop: 8 }}>
          <FieldRow k={act.completed ? 'Azione (fatta)' : 'Azione'} v={`${act.title}${act.description ? ` — ${act.description}` : ''}`} />
          {!act.completed ? (
            <ActionBtn icon="checkmark" label="Segna completata" onPress={() => h.onAdminComplete(i)} loading={h.busy === `admin-${i}`} />
          ) : null}
        </View>
      ))}
      {admin?.due_date ? (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 }}>
          <ActionBtn icon="alarm" label="Promemoria / scadenza ORA" onPress={() => h.onAdminDeadline(false)} loading={h.busy === 'deadline'} />
          <ActionBtn primary icon="logo-google" label="Scadenza su Google" onPress={() => h.onAdminDeadline(true)} loading={h.busy === 'deadline'} />
        </View>
      ) : null}
    </Card>
  );
}

function GenericPanel({
  a, ins,
}: {
  a?: DocumentAnalysisResponse['analysis'];
  ins: DocumentInsights;
}) {
  const resolved = (ins.resolved_fields || []).filter((f) => f.value?.trim());
  return (
    <Card title="Analisi generica" icon="ellipse-outline">
      <FieldRow k="Classificazione" v={[a?.macro_category, a?.subcategory].filter(Boolean).join(' / ')} />
      <FieldRow k="Riepilogo" v={a?.summary} />
      {a?.keywords?.length ? <FieldRow k="Parole chiave" v={a.keywords.join(', ')} /> : null}
      {resolved.map((f, i) => <FieldRow key={i} k={f.label} v={f.value} />)}
    </Card>
  );
}
