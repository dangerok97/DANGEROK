/**
 * Preparare una telefonata: chi chiamare, e cosa manca.
 *
 *     «CHIAMA LORENZO E SPOSTA IL CALCETTO» NON È UN NUMERO.
 *
 * Fra quella frase e lo squillo c'è un passaggio che finora faceva una persona
 * a mano. Questa schermata è quel passaggio: si scrive la frase, ORA cerca chi
 * chiamare, mostra da dove ha preso il numero, e chiede — una cosa per volta —
 * quello che non ha potuto ricavare da sola.
 *
 *     UN NUMERO NUOVO SI CONFERMA. UNO GIÀ CONFERMATO SI MOSTRA.
 *
 * Un numero mai visto — dalla rubrica, dal web, scritto a mano — aspetta un
 * sì, con un pulsante suo: una telefonata parte una volta sola. Uno che la
 * persona aveva già confermato per la stessa persona non si richiede: si dice
 * quale sarà e perché, e resta sempre un pulsante per cambiarlo.
 *
 * Il disegno è quello del resto dell'app — filetti invece di riquadri, un peso
 * solo di testo, colore solo dove qualcosa se l'è guadagnato. L'unica cosa
 * accesa è quello che sta aspettando una risposta.
 */
import { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { api, type MissionPreparation, type PreparationContact } from '@/src/api/client';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { humanizeError } from '@/src/utils/errors';

export default function PreparaChiamata() {
  const { colors } = useTheme();
  const [frase, setFrase] = useState('');
  const [chi, setChi] = useState('');
  const [prep, setPrep] = useState<MissionPreparation | null>(null);
  const [risposta, setRisposta] = useState('');
  const [altroNumero, setAltroNumero] = useState('');
  const [cambio, setCambio] = useState(false);
  const [inCorso, setInCorso] = useState('');
  const [errore, setErrore] = useState<string | null>(null);
  const [chiamata, setChiamata] = useState('');

  const fai = useCallback(
    async (quale: string, azione: () => Promise<{ preparation: MissionPreparation }>) => {
      if (inCorso) return;
      setInCorso(quale);
      setErrore(null);
      try {
        const res = await azione();
        setPrep(res.preparation);
        setRisposta('');
        setAltroNumero('');
        setCambio(false);
      } catch (e) {
        setErrore(humanizeError(e));
      } finally {
        setInCorso('');
      }
    },
    [inCorso],
  );

  const comincia = useCallback(() => {
    if (!frase.trim()) return;
    void fai('start', async () =>
      api.startPreparation(frase.trim(), {
        counterparty: chi.trim() || undefined,
        operation: 'reschedule',
      }),
    );
  }, [frase, chi, fai]);

  const puo = (quale: string) => !!prep?.you_can_answer.includes(quale);

  return (
    <ScrollView
      style={{ backgroundColor: colors.backgroundPrimary }}
      contentContainerStyle={styles.page}
      testID="prepara-chiamata"
    >
      <Text style={[styles.h1, { color: colors.textPrimary }]}>
        Prepara una telefonata
      </Text>
      <Text style={[styles.sub, { color: colors.textSecondary }]}>
        Dimmi cosa vuoi che faccia. Cerco io chi chiamare, e ti chiedo solo
        quello che non riesco a capire da sola.
      </Text>

      {/* ---- la frase ---- */}
      {!prep ? (
        <View style={styles.blocco}>
          <TextInput
            value={frase}
            onChangeText={setFrase}
            placeholder="Es. «Chiama Lorenzo e digli di spostare la partita a calcetto»"
            placeholderTextColor={colors.textTertiary}
            multiline
            testID="prep-request"
            style={[
              styles.input,
              styles.inputAlto,
              { color: colors.textPrimary, borderColor: colors.border },
            ]}
          />
          <TextInput
            value={chi}
            onChangeText={setChi}
            placeholder="Chi devo chiamare? Es. «Lorenzo»"
            placeholderTextColor={colors.textTertiary}
            testID="prep-who"
            style={[
              styles.input,
              { color: colors.textPrimary, borderColor: colors.border },
            ]}
          />
          <Bottone
            label="Preparala"
            testID="prep-start"
            primary
            busy={inCorso === 'start'}
            disabled={!frase.trim()}
            onPress={comincia}
          />
        </View>
      ) : null}

      {prep ? (
        <View style={[styles.scheda, { borderColor: colors.border }]}>
          {/* Quello che è stato chiesto, così com'è stato detto. */}
          <Text style={[styles.chiesto, { color: colors.textTertiary }]}>
            Mi hai chiesto: «{prep.you_asked}»
          </Text>

          <Text style={[styles.stato, { color: colors.textSecondary }]} testID="prep-status">
            {prep.status_label}
          </Text>

          {/* ---- 1 · chi ho trovato, e da dove ---- */}
          {prep.contact ? (
            <View
              style={[
                styles.contatto,
                {
                  borderColor: prep.number_confirmed ? colors.success : colors.warning,
                },
              ]}
              testID="prep-contact"
            >
              <Text style={[styles.nome, { color: colors.textPrimary }]}>
                {prep.contact.name}
              </Text>
              <Text style={[styles.numero, { color: colors.textPrimary }]} testID="prep-number">
                {prep.contact.number}
              </Text>
              {/*
                Da dove viene il numero, sempre.

                «Rubrica» e «Trovato sul web» sono due cose molto diverse
                davanti alla stessa cifra, e chi conferma ha il diritto di
                sapere quale sta guardando.
              */}
              <Text style={[styles.fonte, { color: colors.textSecondary }]} testID="prep-source">
                {prep.contact.source_label}
                {prep.contact.source_detail ? ` — ${prep.contact.source_detail}` : ''}
              </Text>
              {prep.number_confirmed ? (
                <Text style={[styles.ok, { color: colors.success }]} testID="prep-confirmed">
                  ✓ {prep.number_note || 'Numero confermato'}
                </Text>
              ) : null}
              {/*
                Un numero che si usa si può sempre cambiare.

                È la contropartita di non chiederlo ogni volta: la conferma
                non si ripete, ma il pulsante per cambiarlo c'è sempre.
              */}
              {puo('change_number') && !cambio ? (
                <View style={[styles.riga, { marginTop: 8 }]}>
                  <Bottone
                    label="Cambia numero"
                    testID="prep-change-number"
                    onPress={() => setCambio(true)}
                  />
                  <Bottone
                    label="Questo numero è sbagliato"
                    testID="prep-wrong-number"
                    busy={inCorso === 'wrong'}
                    onPress={() =>
                      void fai('wrong', async () =>
                        api.confirmPreparationNumber(prep.preparation_id, false, {
                          operation: 'reschedule',
                        }),
                      )
                    }
                  />
                </View>
              ) : null}
            </View>
          ) : null}

          {/* ---- gli altri numeri trovati, come via d'uscita ---- */}
          {prep.other_candidates?.length ? (
            <View style={styles.blocco} testID="prep-others">
              <Text style={[styles.etichetta, { color: colors.textTertiary }]}>
                Altri numeri trovati
              </Text>
              {prep.other_candidates.map((c: PreparationContact) => (
                <Pressable
                  key={c.number}
                  testID={`prep-other-${c.number}`}
                  onPress={() =>
                    void fai('choose', async () =>
                      api.choosePreparationContact(prep.preparation_id, c.number, 'reschedule'),
                    )
                  }
                  style={({ pressed }: any) => [styles.altro, { opacity: pressed ? 0.6 : 1 }]}
                >
                  <Text style={[styles.sa, { color: colors.textSecondary }]}>
                    {c.number} · {c.source_label}
                    {c.source_detail ? ` — ${c.source_detail}` : ''}
                  </Text>
                </Pressable>
              ))}
            </View>
          ) : null}

          {/* ---- più di uno: si sceglie, non si indovina ---- */}
          {prep.candidates.length > 1 ? (
            <View style={styles.blocco} testID="prep-candidates">
              <Text style={[styles.dice, { color: colors.textPrimary }]}>{prep.says}</Text>
              {prep.candidates.map((c: PreparationContact) => (
                <Pressable
                  key={c.number}
                  testID={`prep-candidate-${c.number}`}
                  onPress={() =>
                    void fai('choose', async () =>
                      api.choosePreparationContact(prep.preparation_id, c.number, 'reschedule'),
                    )
                  }
                  style={({ pressed }: any) => [
                    styles.candidato,
                    { borderColor: colors.border, opacity: pressed ? 0.7 : 1 },
                  ]}
                >
                  <Text style={[styles.nome, { color: colors.textPrimary }]}>{c.name}</Text>
                  <Text style={[styles.numero, { color: colors.textPrimary }]}>{c.number}</Text>
                  <Text style={[styles.fonte, { color: c.trusted ? colors.success : colors.textSecondary }]}>
                    {c.trusted ? '✓ ' : ''}
                    {c.source_label}
                    {c.source_detail ? ` — ${c.source_detail}` : ''}
                  </Text>
                </Pressable>
              ))}
            </View>
          ) : null}

          {/* ---- quello che ORA sapeva già, e che quindi non ha chiesto ---- */}
          {prep.what_ora_knows.length ? (
            <View style={styles.blocco} testID="prep-known">
              <Text style={[styles.etichetta, { color: colors.textTertiary }]}>
                Quello che sapevo già
              </Text>
              {prep.what_ora_knows.map((f: string) => (
                <Text key={f} style={[styles.sa, { color: colors.textSecondary }]}>
                  · {f}
                </Text>
              ))}
            </View>
          ) : null}

          {/* ---- 2 · la domanda, una per volta ---- */}
          {prep.candidates.length <= 1 && !prep.ready ? (
            <Text style={[styles.dice, { color: colors.textPrimary }]} testID="prep-says">
              {prep.says}
            </Text>
          ) : null}

          {/* ---- 3 · il sì o il no sul numero ---- */}
          {puo('confirm_number') ? (
            <View style={styles.riga}>
              <Bottone
                label="Sì, è questo"
                testID="prep-confirm-yes"
                primary
                busy={inCorso === 'yes'}
                onPress={() =>
                  void fai('yes', async () =>
                    api.confirmPreparationNumber(prep.preparation_id, true, {
                      operation: 'reschedule',
                    }),
                  )
                }
              />
              <Bottone
                label="No, non è quello"
                testID="prep-confirm-no"
                busy={inCorso === 'no'}
                onPress={() =>
                  void fai('no', async () =>
                    api.confirmPreparationNumber(prep.preparation_id, false, {
                      operation: 'reschedule',
                    }),
                  )
                }
              />
            </View>
          ) : null}

          {/* ---- il numero me lo dai tu ---- */}
          {puo('give_number') || cambio ? (
            <View style={styles.blocco}>
              <TextInput
                value={altroNumero}
                onChangeText={setAltroNumero}
                placeholder="Scrivi tu il numero da chiamare"
                placeholderTextColor={colors.textTertiary}
                testID="prep-give-number"
                style={[
                  styles.input,
                  { color: colors.textPrimary, borderColor: colors.border },
                ]}
              />
              <Bottone
                label="Usa questo numero"
                testID="prep-use-number"
                disabled={!altroNumero.trim()}
                busy={inCorso === 'altro'}
                onPress={() =>
                  void fai('altro', async () =>
                    api.changePreparationNumber(
                      prep.preparation_id,
                      altroNumero.trim(),
                      'reschedule',
                    ),
                  )
                }
              />
            </View>
          ) : null}

          {/* ---- la risposta a quello che manca ---- */}
          {puo('answer') && prep.question ? (
            <View style={styles.blocco}>
              <TextInput
                value={risposta}
                onChangeText={setRisposta}
                placeholder="Es. «sabato alle 19, al massimo alle 20»"
                placeholderTextColor={colors.textTertiary}
                testID="prep-answer"
                style={[
                  styles.input,
                  { color: colors.textPrimary, borderColor: colors.border },
                ]}
                onSubmitEditing={() => risposta.trim() && void rispondiOra()}
              />
              <Bottone
                label="Rispondi"
                testID="prep-send-answer"
                primary
                disabled={!risposta.trim()}
                busy={inCorso === 'answer'}
                onPress={() => void rispondiOra()}
              />
            </View>
          ) : null}

          {/* ---- 4 · pronta: il riassunto, al futuro ---- */}
          {prep.ready ? (
            <View
              style={[styles.pronta, { borderColor: colors.success }]}
              testID="prep-ready"
            >
              <Text style={[styles.riassunto, { color: colors.textPrimary }]}>
                {prep.summary}
              </Text>
            </View>
          ) : null}

          {/* ---- e comunque la telefonata non parte da qui ---- */}
          {puo('call') ? (
            <View style={styles.blocco}>
              <Bottone
                label="Preparala e chiedimi conferma"
                testID="prep-make-call"
                primary
                busy={inCorso === 'call'}
                onPress={() => {
                  if (inCorso) return;
                  setInCorso('call');
                  setErrore(null);
                  api
                    .preparationToCall(prep.preparation_id, 'reschedule')
                    .then((r: { call_id: string; preparation: MissionPreparation }) => {
                      setChiamata(r.call_id);
                      setPrep(r.preparation);
                    })
                    .catch((e: unknown) => setErrore(humanizeError(e)))
                    .finally(() => setInCorso(''));
                }}
              />
              <Text style={[styles.nota, { color: colors.textTertiary }]}>
                Non compongo niente adesso: preparo la chiamata e ti chiedo il
                via libera prima di farla squillare.
              </Text>
            </View>
          ) : null}

          {chiamata ? (
            <Text style={[styles.ok, { color: colors.success }]} testID="prep-call-ready">
              Chiamata preparata. Manca solo il tuo via libera.
            </Text>
          ) : null}

          {/* ---- il cancello, quando è chiuso ---- */}
          {prep.number_rejected ? (
            <Text style={[styles.bloccata, { color: colors.warning }]} testID="prep-blocked">
              Non telefono a nessuno finché non mi dici qual è il numero giusto.
            </Text>
          ) : null}

          {errore ? (
            <Text style={[styles.bloccata, { color: colors.warning }]} testID="prep-error">
              {errore}
            </Text>
          ) : null}

          <Bottone
            label="Ricomincia"
            testID="prep-reset"
            onPress={() => {
              setPrep(null);
              setChiamata('');
              setFrase('');
              setChi('');
            }}
          />
        </View>
      ) : null}
    </ScrollView>
  );

  function rispondiOra() {
    if (!prep || !risposta.trim()) return;
    void fai('answer', async () =>
      api.answerPreparation(prep.preparation_id, risposta.trim(), {
        field: prep.question?.field,
        operation: 'reschedule',
      }),
    );
  }
}

function Bottone({
  label,
  onPress,
  primary,
  busy,
  disabled,
  testID,
}: {
  label: string;
  onPress: () => void;
  primary?: boolean;
  busy?: boolean;
  disabled?: boolean;
  testID?: string;
}) {
  const { colors } = useTheme();
  const spento = disabled || busy;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: spento }}
      disabled={spento}
      onPress={onPress}
      testID={testID}
      style={({ pressed }: any) => [
        styles.btn,
        {
          backgroundColor: primary ? colors.accentMuted : 'transparent',
          borderColor: primary ? 'transparent' : colors.border,
          opacity: spento ? 0.5 : pressed ? 0.7 : 1,
        },
      ]}
    >
      {busy ? (
        <ActivityIndicator size="small" color={colors.textSecondary} />
      ) : (
        <Text style={[styles.btnLabel, { color: colors.textPrimary }]}>{label}</Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  page: { padding: 20, paddingBottom: 60, gap: 14, maxWidth: 680 },
  h1: { fontSize: 24, fontWeight: '600', letterSpacing: -0.4 },
  sub: { fontSize: 14, lineHeight: 20 },
  blocco: { gap: 10, marginTop: 4 },
  scheda: { borderWidth: StyleSheet.hairlineWidth, borderRadius: 14, padding: 16, gap: 12 },
  chiesto: { fontSize: 12, fontStyle: 'italic' },
  stato: { fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.6 },
  contatto: { borderWidth: StyleSheet.hairlineWidth, borderRadius: 12, padding: 14, gap: 3 },
  candidato: { borderWidth: StyleSheet.hairlineWidth, borderRadius: 12, padding: 14, gap: 3 },
  nome: { fontSize: 16, fontWeight: '600' },
  numero: { fontSize: 20, fontWeight: '500', letterSpacing: 0.4 },
  fonte: { fontSize: 13 },
  ok: { fontSize: 13, fontWeight: '600', marginTop: 4 },
  etichetta: { fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.6 },
  sa: { fontSize: 14, lineHeight: 21 },
  dice: { fontSize: 17, lineHeight: 25, fontWeight: '500' },
  riga: { flexDirection: 'row', gap: 10, flexWrap: 'wrap' },
  altro: { paddingVertical: 4 },
  pronta: { borderWidth: StyleSheet.hairlineWidth, borderRadius: 12, padding: 14 },
  riassunto: { fontSize: 16, lineHeight: 24 },
  nota: { fontSize: 12, lineHeight: 18 },
  bloccata: { fontSize: 14, lineHeight: 21 },
  input: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 15,
  },
  inputAlto: { minHeight: 72, textAlignVertical: 'top' },
  btn: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 999,
    paddingHorizontal: 18,
    paddingVertical: 11,
    alignItems: 'center',
    minWidth: 130,
  },
  btnLabel: { fontSize: 14, fontWeight: '600' },
});

void tokens;
