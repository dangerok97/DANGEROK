/**
 * ORA in sintesi — come stanno le cose, non quando succedono.
 *
 *     QUATTRO NUMERI IN HOME, QUATTRO SEZIONI QUI. GLI STESSI.
 *
 * Il widget in Home conta quattro cose: situazioni attive, domande in attesa,
 * azioni in sospeso, documenti da verificare. «Vedi tutto» apriva l'agenda —
 * cioè un'altra domanda. Qui ognuno di quei quattro numeri diventa la sua
 * sezione, con dentro gli elementi veri.
 *
 * I dati sono gli stessi della Home (`/api/home`), non un secondo conteggio:
 * due superfici che contano per conto loro finiscono per dire numeri diversi,
 * e a quel punto non ci si fida più di nessuna delle due.
 */
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import { api, type HomeV2Response } from '@/src/api/client';
import { OraCard } from '@/src/components/ora-ui';
import { NienteQui, PaginaOra } from '@/src/components/pagine/PaginaOra';
import { ora, oraType } from '@/src/theme/oraSurface';
import { humanizeError } from '@/src/utils/errors';

export default function OraSintesi() {
  const router = useRouter();
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

  const situazione = home?.current_situation;
  const domande = home?.open_questions || [];
  const azioni = (home?.priorities || [])
    .flatMap((g) => g.items || [])
    .filter((i) => i.status !== 'done')
    .slice(0, 8);

  return (
    <PaginaOra
      titolo="ORA in sintesi"
      sottotitolo="Come stanno le cose adesso, voce per voce."
      attiva="index"
      testID="pagina-ora-sintesi"
    >
      {carico ? (
        <ActivityIndicator color={ora.cta} testID="sintesi-carico" />
      ) : errore ? (
        <NienteQui testo={errore} testID="sintesi-errore" />
      ) : (
        <>
          <Sezione
            icona="radio-button-on-outline"
            titolo="Situazioni attive"
            quante={situazione?.indicators?.length ?? 0}
            unita="da seguire"
            vuoto="Nessuna situazione aperta in questo momento."
            testID="sintesi-situazioni"
          >
            {(situazione?.indicators || []).map((i) => (
              <Riga
                key={i.id}
                titolo={i.label}
                meta={i.detail || i.value}
                testID={`sintesi-situazione-${i.id}`}
              />
            ))}
          </Sezione>

          <Sezione
            icona="help-circle-outline"
            titolo="Domande in attesa"
            quante={domande.length}
            unita="da rispondere"
            vuoto="ORA non sta aspettando risposte."
            link={domande.length ? { etichetta: 'Apri le domande', dove: '/domande' } : undefined}
            testID="sintesi-domande"
          >
            {domande.map((q) => (
              <Riga
                key={q.id}
                titolo={q.question}
                meta={q.context_label || q.why_needed || ''}
                onPress={() => router.push('/domande')}
                testID={`sintesi-domanda-${q.id}`}
              />
            ))}
          </Sezione>

          <Sezione
            icona="notifications-outline"
            titolo="Azioni in sospeso"
            quante={situazione?.open_actions_count ?? 0}
            unita="aperte"
            vuoto="Niente in sospeso."
            testID="sintesi-azioni"
          >
            {azioni.map((a) => {
              //     SI APRE DOVE LA HOME APRE, O NON SI APRE.
              // La destinazione di un elemento è scritta nelle sue azioni; se
              // non c'è, la riga resta una riga — non un bottone che non porta
              // da nessuna parte.
              const dove = a.actions?.find((x) => x.route)?.route;
              return (
                <Riga
                  key={a.id}
                  titolo={a.title}
                  meta={a.description || ''}
                  onPress={dove ? () => router.push(dove as never) : undefined}
                  testID={`sintesi-azione-${a.id}`}
                />
              );
            })}
          </Sezione>

          <Sezione
            icona="document-text-outline"
            titolo="Da verificare"
            quante={situazione?.needs_review_count ?? 0}
            unita="documenti"
            vuoto="Nessun documento da controllare."
            link={
              (situazione?.needs_review_count ?? 0) > 0
                ? { etichetta: 'Apri Documenti', dove: '/documenti' }
                : undefined
            }
            testID="sintesi-documenti"
          />
        </>
      )}
    </PaginaOra>
  );
}

function Sezione({
  icona,
  titolo,
  quante,
  unita,
  vuoto,
  link,
  children,
  testID,
}: {
  icona: keyof typeof Ionicons.glyphMap;
  titolo: string;
  quante: number;
  unita: string;
  vuoto: string;
  link?: { etichetta: string; dove: string };
  children?: React.ReactNode;
  testID?: string;
}) {
  const router = useRouter();
  const righe = Array.isArray(children) ? children.filter(Boolean) : children ? [children] : [];

  return (
    <OraCard style={styles.sezione} testID={testID}>
      <View style={styles.testa}>
        <Ionicons name={icona} size={20} color={ora.deep} />
        <Text style={[oraType.section, { color: ora.ink, flex: 1 }]} accessibilityRole="header" aria-level={2}>
          {titolo}
        </Text>
        {/*
          Il numero è quello della Home, non un secondo conteggio: se qui ne
          comparisse uno diverso, nessuno dei due sarebbe più credibile.
        */}
        <Text style={[styles.conta, { color: ora.deep }]} testID={`${testID}-conta`}>
          {quante} {unita}
        </Text>
      </View>

      {righe.length ? righe : <Text style={[oraType.small, { color: ora.ink3 }]}>{vuoto}</Text>}

      {link ? (
        <Pressable
          onPress={() => router.push(link.dove as never)}
          accessibilityRole="button"
          style={({ pressed }) => [styles.link, pressed && { opacity: 0.7 }]}
          testID={`${testID}-link`}
        >
          <Text style={[oraType.small, { color: ora.cta, fontWeight: '600' }]}>{link.etichetta}</Text>
          <Ionicons name="chevron-forward" size={14} color={ora.cta} />
        </Pressable>
      ) : null}
    </OraCard>
  );
}

function Riga({
  titolo,
  meta,
  onPress,
  testID,
}: {
  titolo: string;
  meta?: string;
  onPress?: () => void;
  testID?: string;
}) {
  const corpo = (
    <View style={styles.riga}>
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={[oraType.body, { color: ora.ink }]} numberOfLines={2}>
          {titolo}
        </Text>
        {meta ? (
          <Text style={[oraType.small, { color: ora.ink3 }]} numberOfLines={2}>
            {meta}
          </Text>
        ) : null}
      </View>
      {onPress ? <Ionicons name="chevron-forward" size={15} color={ora.ink3} /> : null}
    </View>
  );

  // Una riga senza dove andare non finge di essere un bottone.
  if (!onPress) return <View testID={testID}>{corpo}</View>;
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      style={({ pressed }) => [pressed && { opacity: 0.7 }]}
      testID={testID}
    >
      {corpo}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  sezione: { gap: 10, padding: 20 },
  testa: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  conta: { fontSize: 13, fontWeight: '600' },
  riga: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingVertical: 10,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: ora.divider,
  },
  link: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingTop: 6 },
});
