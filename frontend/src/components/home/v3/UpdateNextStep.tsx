import { useEffect, useState } from 'react';
import { Pressable, Text, TextInput, View } from 'react-native';
import { useRouter } from 'expo-router';
import { api, type UpdateWork } from '@/src/api/client';
import type { Aggiornamento } from './aggiornamenti';
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
  }, [a.id, a.lavoro]);
  const go = async () => {
    if (busy || (!a.azione && !usesWork)) return;
    setBusy(true); setError('');
    try {
      if (usesWork) {
        setWork(await (isPreparation ? api.runSuggestionWork(a.id, reply) : api.runUpdateWork(a.id, reply))); setReply('');
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
      {work?.result?.question && <Text style={[oraType.body, { color: ora.ink }]}>{work.result.question}</Text>}
      {hasRun && !running && work?.session_id && !['failed', 'interrupted'].includes(work.status) && (
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
