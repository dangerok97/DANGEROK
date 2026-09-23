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
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import { api, type HomeV2Response } from '@/src/api/client';
import { OraBadge, OraCard } from '@/src/components/ora-ui';
import { NienteQui, PaginaOra } from '@/src/components/pagine/PaginaOra';
import {
  comeSiChiama,
  elencoAggiornamenti,
  type Aggiornamento,
} from '@/src/components/home/v3/aggiornamenti';
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

  return (
    <PaginaOra
      titolo="Aggiornamenti di ORA"
      sottotitolo={
        carico
          ? 'Sto mettendo insieme quello che è successo…'
          : righe.length === 0
            ? 'Per ora non è successo niente che valga la pena raccontarti.'
            : righe.length === 1
              ? 'Un aggiornamento.'
              : `${righe.length} aggiornamenti.`
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
        righe.map((a) => <Riga key={a.id} a={a} onRemoved={() => void leggi()} />)
      )}
    </PaginaOra>
  );
}

function Riga({ a, onRemoved }: { a: Aggiornamento; onRemoved: () => void }) {
  const router = useRouter();
  const [removing, setRemoving] = useState(false);
  const [removeError, setRemoveError] = useState('');

  const remove = async () => {
    if (removing) return;
    setRemoving(true);
    setRemoveError('');
    try {
      await rimuoviAggiornamento(a);
      onRemoved();
    } catch (e) {
      setRemoveError(humanizeError(e));
    } finally {
      setRemoving(false);
    }
  };

  return (
    <OraCard style={styles.card} testID={`aggiornamento-${a.id}`}>
      <View style={styles.testa}>
        <OraBadge label={comeSiChiama(a.genere)} tone="info" />
        {a.stato ? (
          <Text style={[oraType.small, { color: ora.ink3 }]} numberOfLines={1}>
            {a.stato}
          </Text>
        ) : null}
      </View>

      <Text style={[oraType.section, { color: ora.ink }]} accessibilityRole="header" aria-level={2}>
        {a.cosa}
      </Text>

      {a.perche ? <Text style={[oraType.body, { color: ora.ink2 }]}>{a.perche}</Text> : null}

      {/* Da dove viene. Sempre, anche quando la risposta è che non si sa. */}
      <Text style={[oraType.small, { color: ora.ink3 }]} testID={`aggiornamento-${a.id}-fonte`}>
        Fonte: {a.fonte}
      </Text>

      {a.non_so ? (
        <Text style={[oraType.small, { color: ora.attention }]}>{a.non_so}</Text>
      ) : null}

      {a.cosa_serve ? (
        <Text style={[oraType.small, { color: ora.deep }]}>{a.cosa_serve}</Text>
      ) : null}

      <View style={styles.cardActions}>
      <Pressable
        onPress={() => router.push(`/aggiornamento/${encodeURIComponent(a.id)}` as never)}
        accessibilityRole="button"
        accessibilityLabel={`Apri i dettagli di ${a.cosa}`}
        style={({ pressed }) => [styles.apri, pressed && { opacity: 0.7 }]}
        testID={`aggiornamento-${a.id}-apri`}
      >
        <Text style={[oraType.small, { color: ora.cta, fontWeight: '600' }]}>Apri dettagli</Text>
        <Ionicons name="chevron-forward" size={14} color={ora.cta} />
      </Pressable>
      <Pressable
        onPress={() => void remove()}
        disabled={removing}
        accessibilityRole="button"
        accessibilityLabel={`Rimuovi ${a.cosa}`}
        style={({ pressed }) => [styles.apri, pressed && { opacity: 0.7 }]}
        testID={`aggiornamento-${a.id}-rimuovi`}
      >
        <Text style={[oraType.small, { color: ora.ink3 }]}>
          {removing ? 'Rimozione…' : 'Non mi interessa'}
        </Text>
      </Pressable>
      </View>
      {removeError ? (
        <Text accessibilityRole="alert" style={[oraType.small, { color: ora.attention }]}>
          {removeError}
        </Text>
      ) : null}
    </OraCard>
  );
}

const styles = StyleSheet.create({
  card: { gap: 10, padding: 20, alignItems: 'flex-start' },
  testa: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  apri: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingTop: 4 },
  cardActions: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 18 },
});
