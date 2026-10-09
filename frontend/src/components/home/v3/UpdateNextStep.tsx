import { useEffect, useState } from 'react';
import { Pressable, Text, TextInput, View } from 'react-native';
import { useRouter } from 'expo-router';
import { api, type UpdateWork } from '@/src/api/client';
import { quandoAggiornamento, type Aggiornamento } from './aggiornamenti';
import { OraCard } from '@/src/components/ora-ui';
import { ora, oraType } from '@/src/theme/oraSurface';
import { humanizeError } from '@/src/utils/errors';

export function UpdateNextStep({ a }: { a: Aggiornamento }) {
  const router = useRouter();
  const [work, setWork] = useState<UpdateWork | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [reply, setReply] = useState('');
  const isPreparation = a.lavoro === 'prepare';
  const usesWork = !!a.lavoro;
  const [loaded, setLoaded] = useState(!usesWork);
  useEffect(() => {
    setWork(null); setReply(''); setLoaded(!usesWork);
    if (!usesWork) return;
    let active = true;
    const read = async () => {
      try { const result = await (isPreparation ? api.getSuggestionWork(a.id) : api.getUpdateWork(a.id)); if (active) { setWork(result); setLoaded(true); setError(''); } }
      catch (e) { if (active) setError(humanizeError(e)); }
    };
    void read();
    const timer = setInterval(() => { void read(); }, 10000);
    return () => { active = false; clearInterval(timer); };
  }, [a.id, isPreparation, usesWork]);
  const go = async () => {
    if (busy || (!a.azione && !usesWork)) return;
    setBusy(true); setError('');
    try {
      if (usesWork) {
        setWork(await (isPreparation ? api.runSuggestionWork(a.id, reply) : api.runUpdateWork(a.id, reply, work?.question_revision))); setReply('');
      } else if (a.azione?.kind === 'suggestion') {
        const accepted = await api.acceptSuggestion(a.id);
        const result = accepted.result as any;
        const route = result?.route || result?.result?.route || a.azione.route;
        if (route?.startsWith('/') && !route.startsWith('//')) router.push({ pathname: route, params: a.azione.params } as any);
        else setWork({ status: 'ready', message: 'Risposta registrata. Riapri gli aggiornamenti per vedere lo stato aggiornato.' });
      } else if (a.azione?.route?.startsWith('/') && !a.azione.route.startsWith('//')) {
        router.push({ pathname: a.azione.route, params: a.azione.params } as any);
      }
    } catch (e) { setError(humanizeError(e)); }
    finally { setBusy(false); }
  };
  const running = busy || work?.status === 'running';
  const hasRun = !!work && work.status !== 'not_started';
  const situation = a.situazione;
  const [situationBusy, setSituationBusy] = useState(false);
  const [situationError, setSituationError] = useState('');
  const openSituationConversation = (draft: string) => {
    if (!situation) return;
    const path = situation.session_id
      ? `/ora/${encodeURIComponent(situation.session_id)}`
      : '/ora';
    router.push(`${path}?draft=${encodeURIComponent(draft)}` as never);
  };
  const situationDecision = async (decision: 'stop_alerts' | 'resolved') => {
    if (!situation || situationBusy) return;
    setSituationBusy(true); setSituationError('');
    try {
      await api.stopSituationAlerts(a.id, decision, situation.revision);
      router.replace('/aggiornamenti' as never);
    } catch (e) { setSituationError(humanizeError(e)); }
    finally { setSituationBusy(false); }
  };
  if (a.solo_informazione) {
    return (
      <OraCard style={{ padding: 20, gap: 12 }} testID="aggiornamento-solo-informativo">
        <Text style={[oraType.section, { color: ora.ink }]}>Una segnalazione, non un compito</Text>
        <Text style={[oraType.body, { color: ora.ink2 }]}>
          ORA ti ha riportato un'informazione, ma da questa scheda non risulta
          un'azione concreta da svolgere né un monitoraggio automatico confermato.
          Una previsione non è la prova che l'evento si sia verificato.
        </Text>
        {a.fonte && <Text style={[oraType.small, { color: ora.ink2 }]}>
          Fonte indicata: {a.fonte}
        </Text>}
        {!!a.scade && <Text style={[oraType.small, { color: ora.ink2 }]}>
          Questa segnalazione resta utile fino a: {quandoAggiornamento(a.scade) || a.scade}.
          La scadenza dell'avviso non conferma che il fatto sia avvenuto.
        </Text>}
        {usesWork && !loaded && !error && <Text>Sto recuperando la verifica precedente…</Text>}
        {work?.result?.ora_text && <View style={{ gap: 6 }}>
          <Text style={[oraType.small, { color: ora.ink3 }]}>Ultima risposta di ORA (non equivale a un monitoraggio attivo)</Text>
          <Text style={[oraType.body, { color: ora.ink }]}>{work.result.ora_text}</Text>
        </View>}
        {work?.status === 'failed' && <Text style={[oraType.small, { color: ora.attention }]}>
          L'ultima verifica non è riuscita: l'informazione non è stata confermata.
        </Text>}
        {work?.session_id && <Pressable accessibilityRole="link"
          onPress={() => router.push(`/ora/${encodeURIComponent(work.session_id!)}` as never)}>
          <Text style={{ color: ora.cta }}>Rivedi la conversazione precedente →</Text>
        </Pressable>}
        {!!error && <Text accessibilityRole="alert" style={{ color: ora.attention }}>{error}</Text>}
        {!!a.azione?.route && <Pressable accessibilityRole="button"
          testID="approfondisci-aggiornamento"
          onPress={() => router.push({
            pathname: a.azione!.route!, params: a.azione!.params,
          } as any)}
          style={{ padding: 12, borderRadius: 12, backgroundColor: ora.cta, alignSelf: 'flex-start' }}>
          <Text style={{ color: '#fff', fontWeight: '600' }}>Approfondisci con ORA</Text>
        </Pressable>}
      </OraCard>
    );
  }
  if (situation) {
    const followupConfirmed = ['scheduled', 'due', 'running'].includes(situation.followup_status || '');
    return (
      <OraCard style={{ padding: 20, gap: 12 }} testID="dettaglio-situazione-monitorata">
        <Text style={[oraType.section, { color: ora.ink }]}>Cosa sta seguendo ORA</Text>
        <Text style={[oraType.body, { color: ora.ink }]}>{situation.summary}</Text>
        {situation.current_state && <Text style={[oraType.body, { color: ora.ink2 }]}>Ultimo stato noto: {situation.current_state}</Text>}
        <Text style={[oraType.small, { color: ora.ink2 }]}>
          Registrata: {quandoAggiornamento(situation.created_at) || 'data non disponibile'}
        </Text>
        {(situation.reason || situation.purpose) && <Text style={[oraType.body, { color: ora.ink2 }]}>
          Perché la controllo: {situation.purpose || situation.reason}
        </Text>}
        {situation.expected_outcome && <Text style={[oraType.body, { color: ora.ink2 }]}>
          Cosa vogliamo sapere: {situation.expected_outcome}
        </Text>}
        {situation.notify_when && <Text style={[oraType.body, { color: ora.ink }]}>
          Quando ti avviso: {situation.notify_when}
        </Text>}
        <Text style={[oraType.body, { color: ora.ink2 }]}>
          {followupConfirmed
            ? situation.followup_status === 'running'
              ? 'Il controllo è in corso.'
              : situation.next_check_label
                ? `Prossimo controllo: ${situation.next_check_label}.`
                : 'È registrato un controllo; il suo orario non è disponibile.'
            : 'Non risulta un prossimo controllo confermato: ORA non promette notifiche automatiche.'}
        </Text>
        {situation.last_checked_at && <Text style={[oraType.small, { color: ora.ink2 }]}>
          Ultima verifica: {quandoAggiornamento(situation.last_checked_at)}
          {situation.last_result ? ` · ${situation.last_result}` : ''}
        </Text>}
        {a.cosa_serve && <Text style={[oraType.body, { color: ora.ink }]}>Domanda per te: {a.cosa_serve}</Text>}
        <Text style={[oraType.small, { color: ora.ink2 }]}>
          ORA può valutare previsioni e segnali disponibili, ma non può osservare direttamente
          lo stato fisico della situazione. I pulsanti per aggiornarla aprono un messaggio
          pronto da inviare: puoi modificarlo e confermarlo in chat.
        </Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
          <Pressable accessibilityRole="button" testID="situazione-non-ancora"
            onPress={() => openSituationConversation(
              `Per la situazione «${situation.summary}»: non è ancora raggiunto il risultato. Ricontrolla le condizioni con dati aggiornati e, se possibile, programma un nuovo controllo utile senza inventare l'esito.`
            )} style={{ padding: 12, borderRadius: 10, borderWidth: 1, borderColor: ora.ink3 }}>
            <Text style={{ color: ora.deep }}>Non ancora · Rispondi a ORA</Text>
          </Pressable>
          <Pressable accessibilityRole="button" testID="situazione-cambiata"
            onPress={() => openSituationConversation(
              `La situazione «${situation.summary}» è cambiata: `
            )} style={{ padding: 12, borderRadius: 10, borderWidth: 1, borderColor: ora.ink3 }}>
            <Text style={{ color: ora.deep }}>È cambiata · Spiega a ORA</Text>
          </Pressable>
          <Pressable accessibilityRole="button" testID="situazione-conclusa"
            disabled={situationBusy} onPress={() => void situationDecision('resolved')}
            style={{ padding: 12, borderRadius: 10, backgroundColor: ora.cta }}>
            <Text style={{ color: '#fff', fontWeight: '600' }}>Situazione conclusa</Text>
          </Pressable>
          <Pressable accessibilityRole="button" testID="situazione-niente-avvisi"
            disabled={situationBusy} onPress={() => void situationDecision('stop_alerts')}
            style={{ padding: 12, borderRadius: 10, borderWidth: 1, borderColor: ora.ink3 }}>
            <Text style={{ color: ora.ink2 }}>Ok grazie · Basta avvisi</Text>
          </Pressable>
        </View>
        {!!situationError && <Text accessibilityRole="alert" style={{ color: ora.attention }}>{situationError}</Text>}
      </OraCard>
    );
  }
  return (
    <OraCard style={{ padding: 20, gap: 12 }} testID="dettaglio-passo">
      <Text style={[oraType.section, { color: ora.ink }]}>Prossimo passo</Text>
      <Text style={[oraType.body, { color: ora.ink2 }]}>{a.prossimo_passo || 'Non è disponibile un’azione eseguibile per questo aggiornamento.'}</Text>
      {a.preparazione && <View style={{ gap: 10 }}>
        {a.preparazione.options?.map((option, index) => <View key={`${option.event_id}:${index}`} style={{ gap: 4 }}>
          <Text style={[oraType.body, { color: ora.ink }]}>{option.title}</Text>
          <Text style={[oraType.body, { color: ora.ink2 }]}>{new Date(option.starts_at).toLocaleString('it-IT')} – {new Date(option.ends_at).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })}</Text>
        </View>)}
        <Text style={[oraType.small, { color: ora.ink2 }]}>{a.preparazione.limits}</Text>
        {!!a.preparazione.checked_at && <Text style={[oraType.small, { color: ora.ink2 }]}>Controllo eseguito: {new Date(a.preparazione.checked_at).toLocaleString('it-IT')}. Nessun appuntamento modificato.</Text>}
      </View>}
      {usesWork && !loaded && !error && <Text>Caricamento dell’attività…</Text>}
      {running && <Text accessibilityLiveRegion="polite">Verifica in corso…</Text>}
      {work?.message && <Text>{work.message}</Text>}
      {work?.result?.ora_text && <Text style={[oraType.body, { color: ora.ink }]}>{work.result.ora_text}</Text>}
      {work?.status === 'failed' && <Text>La verifica non è stata completata. L’aggiornamento resta da chiarire.</Text>}
      {hasRun && !running && !['failed', 'interrupted'].includes(work?.status || '') && <Text style={[oraType.small, { color: ora.ink2 }]}>Risposta di ORA · l’aggiornamento non viene chiuso automaticamente.</Text>}
      {work?.result?.sources?.map((source, index) => <Text key={index} style={[oraType.small, { color: ora.ink2 }]}>Fonte consultata: {source.title || source.url}</Text>)}
      {work?.result?.pending_turn?.status === 'awaiting_client' && <Text>Serve un passaggio sul dispositivo. Apri la sessione per completarlo.</Text>}
      {work?.session_id && <Pressable accessibilityRole="link" onPress={() => router.push(`/ora/${encodeURIComponent(work.session_id!)}` as never)}><Text style={{ color: ora.cta }}>Apri la stessa sessione per ulteriori operazioni →</Text></Pressable>}
      {work?.result?.route?.startsWith('/ora?') && <Pressable accessibilityRole="link" onPress={() => router.push(work.result!.route as never)}><Text style={{ color: ora.cta }}>Continua con ORA →</Text></Pressable>}
      {work?.result?.question && <Text style={[oraType.body, { color: ora.ink }]}>{work.result.question}</Text>}
      {hasRun && !running && (work?.session_id || work?.question_revision) && !['failed', 'interrupted'].includes(work.status) && (
        <TextInput accessibilityLabel="Risposta sul prossimo passo" placeholder="Rispondi o chiedi un chiarimento…" value={reply} onChangeText={setReply} maxLength={2000} multiline style={{ borderWidth: 1, borderColor: ora.ink3, borderRadius: 12, padding: 12, color: ora.ink }} />
      )}
      {!!error && <Text accessibilityRole="alert" style={{ color: ora.attention }}>{error}</Text>}
      {usesWork && (!!error || ['failed', 'interrupted'].includes(work?.status || '')) && !busy && <Pressable accessibilityRole="button" onPress={async () => {
        setBusy(true);
        try { setWork(await (isPreparation ? api.getSuggestionWork(a.id) : api.getUpdateWork(a.id))); setLoaded(true); setError(''); }
        catch (e) { setError(humanizeError(e)); }
        finally { setBusy(false); }
      }}><Text style={{ color: ora.cta }}>Ricontrolla lo stato</Text></Pressable>}

      {(a.azione || (usesWork && hasRun)) && !running && loaded && (!hasRun || (!!reply.trim() && !['failed', 'interrupted'].includes(work?.status || ''))) && (
        <Pressable accessibilityRole="button" onPress={() => void go()} style={{ backgroundColor: ora.cta, borderRadius: 12, padding: 14, alignSelf: 'flex-start' }}>
          <Text style={{ color: '#fff', fontWeight: '600' }}>{hasRun ? 'Invia risposta' : a.azione?.label}</Text>
        </Pressable>
      )}
      {!a.azione && !hasRun && <Text style={[oraType.small, { color: ora.ink2 }]}>Questa scheda è informativa: ORA non ha ancora un’azione disponibile.</Text>}
    </OraCard>
  );
}
