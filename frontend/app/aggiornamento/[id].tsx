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
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams } from 'expo-router';

import { api, type HomeV2Response } from '@/src/api/client';
import { OraBadge, OraCard } from '@/src/components/ora-ui';
import { NienteQui, PaginaOra } from '@/src/components/pagine/PaginaOra';
import {
  comeSiChiama,
  elencoAggiornamenti,
  type Aggiornamento,
} from '@/src/components/home/v3/aggiornamenti';
import { ora, oraType } from '@/src/theme/oraSurface';
import { humanizeError } from '@/src/utils/errors';

export default function DettaglioAggiornamento() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [home, setHome] = useState<HomeV2Response | null>(null);
  const [errore, setErrore] = useState<string | null>(null);
  const [fallback, setFallback] = useState<Aggiornamento | null>(null);
  const [carico, setCarico] = useState(true);

  const leggi = useCallback(async () => {
    setCarico(true);
    try {
      const result = await api.getHome();
      setHome(result);
      if (!elencoAggiornamenti(result).some(x => x.id === id)) {
        try { const opportunity = await api.getOpportunity(String(id)); setFallback(elencoAggiornamenti({ opportunities: [opportunity] } as HomeV2Response)[0] || null); } catch { setFallback(null); }
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
      titolo="Aggiornamento di ORA"
      sottotitolo={a ? comeSiChiama(a.genere) : undefined}
      attiva="index"
      testID="pagina-aggiornamento"
    >
      {carico ? (
        <ActivityIndicator color={ora.cta} testID="dettaglio-carico" />
      ) : errore ? (
        <NienteQui testo={errore} testID="dettaglio-errore" />
      ) : !a ? (
        <NienteQui
          testo="Questo aggiornamento non è più fra quelli attivi: può essere stato chiuso o superato."
          testID="dettaglio-mancante"
        />
      ) : (
        <Dettaglio a={a} />
      )}
    </PaginaOra>
  );
}

function Dettaglio({ a }: { a: Aggiornamento }) {
  return (
    <>
      {a.stato ? (
        <View style={styles.statoRiga} testID="dettaglio-stato">
          <OraBadge label={a.stato} tone="info" />
        </View>
      ) : null}

      <Voce
        icona="information-circle-outline"
        titolo={a.genere === 'occasione' ? 'Segnalazione da verificare' : 'Cosa è successo'}
        testo={a.cosa}
        testID="dettaglio-cosa"
      />

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
});
