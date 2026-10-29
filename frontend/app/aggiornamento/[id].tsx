import { UpdateNextStep } from '@/src/components/home/v3/UpdateNextStep';
/**
 * Il dettaglio di un aggiornamento — quello, non un altro.
 *
 *     «APRI DETTAGLI» DEVE APRIRE I DETTAGLI DI QUESTA COSA QUI.
 *
 * Il bottone non apriva niente. Adesso porta qui, con l'identificativo
 * dell'aggiornamento nell'indirizzo: la pagina si può aprire anche da un link
 * diretto o dopo un refresh, e mostra sempre la stessa cosa.
 *
 * Il contenuto è il contratto del V3.21.3a, riga per riga. Quando una di
 * quelle righe non esiste, si dice che non esiste: «originale non
 * disponibile» compare anche qui, per intero, invece di sparire come se la
 * domanda non fosse stata fatta.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';

import { api, type HomeV2Response } from '@/src/api/client';
import { OraBadge, OraCard } from '@/src/components/ora-ui';
import { NienteQui, PaginaOra } from '@/src/components/pagine/PaginaOra';
import {
  comeSiChiamaQuesto,
  quandoAggiornamento,
  elencoAggiornamenti,
  type Aggiornamento,
} from '@/src/components/home/v3/aggiornamenti';
import { rimuoviAggiornamento } from '@/src/components/home/v3/rimuoviAggiornamento';
import { ora, oraType } from '@/src/theme/oraSurface';
import { humanizeError } from '@/src/utils/errors';

export default function DettaglioAggiornamento() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [home, setHome] = useState<HomeV2Response | null>(null);
  const [errore, setErrore] = useState<string | null>(null);
  const [fallback, setFallback] = useState<Aggiornamento | null>(null);
  const [carico, setCarico] = useState(true);

  const leggi = useCallback(async () => {
    setCarico(true);
    setHome(null);
    setFallback(null);
    try {
      // Detail is durable and independent of Home ranking/expiration.
      if (String(id).startsWith('psug_')) {
        const result = await api.getSuggestion(String(id));
        setFallback(elencoAggiornamenti({ ora_ti_consiglia: [result.suggestion] } as HomeV2Response)[0] || null);
        setErrore(null);
        return;
      }
      if (String(id).startsWith('gol_')) {
        try {
          const goal = await api.getAgentGoal(String(id));
          setFallback(elencoAggiornamenti({ agent_work: [goal] } as HomeV2Response)[0] || null);
        } catch (e: any) {
          // A bookmarked URL for a finished trip is an expired update, not
          // an error that asks the user to retry or grant permission.
          if (e?.status !== 404 && e?.status !== 410) throw e;
          setFallback(null);
        }
        setErrore(null);
        return;
      }
      const result = await api.getHome();
      setHome(result);
      if (!elencoAggiornamenti(result).some(x => x.id === id)) {
        try {
          const opportunity = await api.getOpportunity(String(id));
          setFallback(elencoAggiornamenti({ opportunities: [opportunity] } as HomeV2Response)[0] || null);
        } catch { setFallback(null); }
      }
      setErrore(null);
    } catch (e) {
      setErrore(humanizeError(e));
    } finally {
      setCarico(false);
    }
  }, [id]);

  useEffect(() => {
    void leggi();
  }, [leggi]);

  const a = elencoAggiornamenti(home).find((x) => x.id === String(id || '')) || fallback;

  return (
    <PaginaOra
      titolo={a?.promemoria === 'reminder' ? 'Promemoria' : a?.promemoria === 'phone_call' ? 'Telefonata'
        : a?.promemoria === 'morning_brief' ? 'Il punto del mattino' : 'Aggiornamento di ORA'}
      sottotitolo={a ? comeSiChiamaQuesto(a) : undefined}
      attiva="index"
      testID="pagina-aggiornamento"
    >
      {carico ? (
        <ActivityIndicator color={ora.cta} testID="dettaglio-carico" />
      ) : errore ? (
        <NienteQui testo={errore} testID="dettaglio-errore" />
      ) : !a ? (
        <NienteQui
          testo="Questo aggiornamento è scaduto o non è più attivo. ORA non ti chiederà di risolvere un evento già passato."
          testID="dettaglio-mancante"
        />
      ) : a.promemoria ? (
        <DettaglioPromemoria a={a} onClosed={() => router.replace('/' as never)} />
      ) : (
        <Dettaglio a={a} onRemoved={() => router.replace('/aggiornamenti' as never)} onChanged={leggi} />
      )}
    </PaginaOra>
  );
}

export const RIMANDI: Array<{ minuti: number; label: string }> = [
  { minuti: 10, label: 'Tra 10 minuti' },
  { minuti: 60, label: 'Tra un\'ora' },
];

/**
 * Un promemoria che hai chiesto tu, o l'esito di una telefonata che hai
 * chiesto tu. Non «una cosa che ho notato» e niente da verificare
 * (screenshot del 27/10): la frase, quando, e cosa puoi farci.
 */
function DettaglioPromemoria({ a, onClosed }: { a: Aggiornamento; onClosed: () => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [errore, setErrore] = useState('');
  const [fatto, setFatto] = useState('');
  const agisci = async (azione: 'done' | 'snooze', minuti = 10) => {
    if (busy) return;
    setBusy(azione + minuti);
    setErrore('');
    try {
      const r = await api.reminderAction(a.id, azione, minuti);
      if (azione === 'snooze' && r.due_at) {
        const ora = new Date(r.due_at).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
        setFatto(`Va bene, te lo ricordo alle ${ora}.`);
        setTimeout(onClosed, 1200);
      } else {
        onClosed();
      }
    } catch (e) {
      setErrore(humanizeError(e));
    } finally {
      setBusy(null);
    }
  };
  // A call outcome and the morning brief are news to read: «Ok», no snooze.
  const telefonata = a.promemoria === 'phone_call' || a.promemoria === 'morning_brief';
  return (
    <>
      <OraCard style={styles.voce} testID="promemoria-testo">
        <View style={styles.testa}>
          <Ionicons name={a.promemoria === 'morning_brief' ? 'sunny-outline' : telefonata ? 'call-outline' : 'alarm-outline'} size={18} color={ora.deep} />
          <Text style={[oraType.small, { color: ora.ink3, fontWeight: '600' }]}>
            {(quandoAggiornamento(a.quando) || '').toUpperCase()}
          </Text>
        </View>
        <Text style={[oraType.title, { color: ora.ink }]}>{a.cosa}</Text>
      </OraCard>
      {fatto ? (
        <Text accessibilityRole="alert" style={[oraType.body, { color: ora.ink }]} testID="promemoria-rimandato">{fatto}</Text>
      ) : (
        <View style={styles.bottoni}>
          <Pressable accessibilityRole="button" testID="promemoria-fatto"
            onPress={() => void agisci('done')} disabled={!!busy}
            style={({ pressed }) => [styles.retry, pressed && { opacity: 0.8 }]}>
            <Text style={{ color: '#fff', fontWeight: '600' }}>{busy === 'done10' ? '…' : telefonata ? 'Ok' : 'Fatto'}</Text>
          </Pressable>
          {!telefonata && RIMANDI.map(r => (
            <Pressable key={r.minuti} accessibilityRole="button" testID={`promemoria-rimanda-${r.minuti}`}
              onPress={() => void agisci('snooze', r.minuti)} disabled={!!busy}
              style={({ pressed }) => [styles.secondario, pressed && { opacity: 0.8 }]}>
              <Text style={{ color: ora.ink, fontWeight: '600' }}>{busy === 'snooze' + r.minuti ? '…' : r.label}</Text>
            </Pressable>
          ))}
        </View>
      )}
      {errore ? <Text accessibilityRole="alert" style={{ color: ora.attention }}>{errore}</Text> : null}
    </>
  );
}

function Dettaglio({ a, onRemoved, onChanged }: { a: Aggiornamento; onRemoved: () => void; onChanged: () => Promise<void> }) {
  const [removing, setRemoving] = useState(false);
  const [removeError, setRemoveError] = useState('');
  const retryInFlight = useRef(false);
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState('');
  const retry = async () => {
    if (retryInFlight.current || !a.retry_available) return;
    retryInFlight.current = true;
    setRetrying(true); setRetryError('');
    try {
      const result = await api.retryAgentGoal(a.id);
      if (!result.ok) throw new Error('Non sono riuscita a programmare la ripresa. Riprova tra poco.');
      await onChanged();
    } catch (e) { setRetryError(humanizeError(e)); }
    finally { retryInFlight.current = false; setRetrying(false); }
  };
  const remove = async () => {
    if (removing) return;
    setRemoving(true);
    setRemoveError('');
    try { await rimuoviAggiornamento(a); onRemoved(); }
    catch (e) { setRemoveError(humanizeError(e)); }
    finally { setRemoving(false); }
  };
  return (
    <>
      {a.stato ? (
        <View style={styles.statoRiga} testID="dettaglio-stato">
          <OraBadge label={a.stato} tone="info" />
        </View>
      ) : null}

      <Voce
        icona="time-outline"
        titolo="Quando è nato e fino a quando serve"
        testo={`Creato: ${quandoAggiornamento(a.quando) || 'data non disponibile'}\n${a.scade ? `Scade: ${quandoAggiornamento(a.scade) || a.scade}` : 'Scadenza non indicata dalla fonte'}`}
        testID="dettaglio-scadenza"
      />
      <Voce
        icona="information-circle-outline"
        titolo={a.genere === 'occasione'
          ? (a.solo_informazione ? 'Informazione da una fonte' : 'Segnalazione da verificare')
          : 'Cosa è successo'}
        testo={a.cosa}
        testID="dettaglio-cosa"
      />

      {a.retry_available && <OraCard style={styles.voce} testID="dettaglio-ripresa">
        <Text style={[oraType.body, { color: ora.ink }]}>
          Il lavoro è conservato. Puoi farlo ripartire senza riscrivere la richiesta.
        </Text>
        <Pressable accessibilityRole="button" testID="riprova-lavoro"
          onPress={() => void retry()} disabled={retrying || removing}
          accessibilityState={{ disabled: retrying || removing, busy: retrying }}
          style={({ pressed }) => [styles.retry, pressed && { opacity: 0.8 }]}>
          <Text style={{ color: '#fff', fontWeight: '600' }}>{retrying ? 'Ripresa in preparazione…' : 'Riprova'}</Text>
        </Pressable>
        {!!retryError && <Text accessibilityRole="alert" style={{ color: ora.attention }}>{retryError}</Text>}
      </OraCard>}

      <Pressable
        accessibilityRole="button"
        onPress={() => void remove()}
        disabled={removing || retrying}
        style={({ pressed }) => [styles.remove, pressed && { opacity: 0.7 }]}
        testID="dettaglio-rimuovi"
      >
        <Text style={[oraType.body, { color: ora.ink3 }]}>
          {removing ? 'Rimozione…' : 'Non mi interessa'}
        </Text>
      </Pressable>
      {removeError ? <Text accessibilityRole="alert" style={{ color: ora.attention }}>{removeError}</Text> : null}

      <UpdateNextStep a={a} />

      {/*
        La provenienza è la riga che regge tutte le altre: senza, questa pagina
        dice cose sulla vita di qualcuno senza dire come fa a saperle.
      */}
      <Voce
        icona="git-branch-outline"
        titolo="Da dove viene"
        testo={a.fonte}
        mancante="Fonte non disponibile"
        nota={a.non_so}
        testID="dettaglio-fonte"
      />

      <Voce
        icona="heart-outline"
        titolo="Perché conta"
        testo={a.perche}
        mancante="Non ho una ragione da darti oltre al fatto che l'ho notato."
        testID="dettaglio-perche"
      />

      {a.genere !== 'occasione' && <Voce
        icona="sync-outline"
        titolo="Attività in corso"
        testo={a.cosa_sta_facendo}
        mancante="Nessuna attività avviata da questa segnalazione."
        testID="dettaglio-facendo"
      />}

      {a.testo_preparato ? <Voce
        icona="document-text-outline"
        titolo="Risultato preparato"
        testo={a.testo_preparato}
        mancante=""
        nota="Bozza basata sulle informazioni disponibili; nessuna azione esterna eseguita."
        testID="dettaglio-risultato"
      /> : null}

      <Voce
        icona="hand-left-outline"
        titolo="Cosa serve a te"
        testo={a.cosa_serve}
        mancante="Nessuna richiesta specifica al momento."
        testID="dettaglio-serve"
      />


    </>
  );
}

/**
 * Una riga del contratto.
 *
 * `mancante` è la frase da dire quando la cosa non c'è: lasciare il posto
 * vuoto farebbe sembrare che la domanda non fosse stata fatta.
 */
function Voce({
  icona,
  titolo,
  testo,
  nota,
  mancante,
  testID,
}: {
  icona: keyof typeof Ionicons.glyphMap;
  titolo: string;
  testo?: string;
  nota?: string;
  mancante?: string;
  testID?: string;
}) {
  const contenuto = (testo || '').trim();
  if (!contenuto && !mancante) return null;

  return (
    <OraCard style={styles.voce} testID={testID}>
      <View style={styles.testa}>
        <Ionicons name={icona} size={18} color={ora.deep} />
        <Text style={[oraType.small, { color: ora.ink3, fontWeight: '600' }]}>
          {titolo.toUpperCase()}
        </Text>
      </View>
      <Text style={[oraType.body, { color: contenuto ? ora.ink : ora.ink3 }]}>
        {contenuto || mancante}
      </Text>
      {nota ? <Text style={[oraType.small, { color: ora.attention }]}>{nota}</Text> : null}
    </OraCard>
  );
}

const styles = StyleSheet.create({
  statoRiga: { flexDirection: 'row' },
  voce: { gap: 8, padding: 20, alignItems: 'flex-start' },
  testa: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  remove: { alignSelf: 'flex-start', paddingVertical: 10 },
  retry: { minHeight: 44, padding: 12, borderRadius: 12, backgroundColor: ora.cta, alignSelf: 'flex-start' },
  secondario: { minHeight: 44, padding: 12, borderRadius: 12, borderWidth: 1, borderColor: ora.hairline, alignSelf: 'flex-start' },
  bottoni: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
});
