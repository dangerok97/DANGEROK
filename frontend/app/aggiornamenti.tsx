/**
 * Aggiornamenti di ORA — che cosa sta succedendo, per esteso.
 *
 *     UN NUMERO CHE NON SI PUÒ APRIRE NON È UN AGGIORNAMENTO: È UN'ETICHETTA.
 *
 * «1 aggiornamento» in Home non apriva niente. Qui c'è l'elenco, costruito
 * dallo stesso insieme che la Home conta (`elencoAggiornamenti`), così i due
 * numeri non possono scollarsi.
 *
 * Ogni riga porta il contratto del V3.21.3a — cosa, fonte, perché conta,
 * stato, cosa serve — e «Apri dettagli» porta al dettaglio di *quello*
 * aggiornamento, non a una pagina generica.
 */
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';

import { api, type HomeV2Response } from '@/src/api/client';
import { NienteQui, PaginaOra } from '@/src/components/pagine/PaginaOra';
import { elencoAggiornamenti, type Aggiornamento } from '@/src/components/home/v3/aggiornamenti';
import { UpdatesBoard, sintesiAggiornamenti } from '@/src/components/home/v3/UpdatesBoard';
import { rimuoviAggiornamento } from '@/src/components/home/v3/rimuoviAggiornamento';
import { ora, oraType } from '@/src/theme/oraSurface';
import { humanizeError } from '@/src/utils/errors';

export default function Aggiornamenti() {
  const [home, setHome] = useState<HomeV2Response | null>(null);
  const [errore, setErrore] = useState<string | null>(null);
  const [carico, setCarico] = useState(true);

  const leggi = useCallback(async () => {
    setCarico(true);
    try {
      setHome(await api.getHome());
      setErrore(null);
    } catch (e) {
      setErrore(humanizeError(e));
    } finally {
      setCarico(false);
    }
  }, []);

  useEffect(() => {
    void leggi();
  }, [leggi]);

  const righe = elencoAggiornamenti(home);
  const router = useRouter();
  const [removeError, setRemoveError] = useState('');

  const rimuovi = async (a: Aggiornamento) => {
    setRemoveError('');
    try {
      await rimuoviAggiornamento(a);
      await leggi();
    } catch (e) {
      setRemoveError(humanizeError(e));
    }
  };

  return (
    <PaginaOra
      titolo="Aggiornamenti"
      sottotitolo={
        carico
          ? 'Sto mettendo insieme quello che è successo…'
          : righe.length === 0
            ? 'Per ora non è successo niente che valga la pena raccontarti.'
            : sintesiAggiornamenti(righe)
      }
      attiva="index"
      testID="pagina-aggiornamenti"
    >
      {carico ? (
        <ActivityIndicator color={ora.cta} testID="aggiornamenti-carico" />
      ) : errore ? (
        <NienteQui testo={errore} testID="aggiornamenti-errore" />
      ) : righe.length === 0 ? (
        <NienteQui
          testo="Quando ORA farà qualcosa per te, lo troverai qui con la sua fonte."
          testID="aggiornamenti-vuoto"
        />
      ) : (
        <View style={styles.wrap}>
          <UpdatesBoard
            righe={righe}
            onOpen={(a) => router.push(`/aggiornamento/${encodeURIComponent(a.id)}` as never)}
            onDismiss={rimuovi}
            testIdFor={(a) => `aggiornamento-${a.id}`}
          />
          {removeError ? (
            <Text accessibilityRole="alert" style={[oraType.small, { color: ora.attention }]}>
              {removeError}
            </Text>
          ) : null}
        </View>
      )}
    </PaginaOra>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 8, width: '100%', maxWidth: 640, alignSelf: 'center' },
});
