/**
 * Prepariamo la tua telefonata — la superficie, V3.21.3.
 *
 *     «CHIAMA LORENZO E SPOSTA IL CALCETTO» NON È UN NUMERO.
 *
 * Fra quella frase e lo squillo c'è un passaggio: ORA cerca chi chiamare,
 * dice da dove ha preso il numero, e chiede — una cosa per volta — quello che
 * non riesce a ricavare da sola. La logica è quella di V3.20/V3.21 e non è
 * cambiata: qui cambia come si legge.
 *
 * Tre passi, nell'ordine in cui contano: chi ho trovato, che cosa dirò e cosa
 * non dirò, e solo alla fine il via libera. A destra, la richiesta così com'è
 * stata scritta e il riepilogo di quello che partirà — mai un mission_id, mai
 * uno stato interno.
 */
import { useCallback, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { api, type MissionPreparation, type PreparationContact } from '@/src/api/client';
import { IconBubble, OraBadge, OraButton, OraCard } from '@/src/components/ora-ui';
import { DesktopShell } from '@/src/shell';
import { Avatar } from '@/src/shell/RailAccount';
import { useBreakpoint } from '@/src/theme/responsive';
import { ora, oraType } from '@/src/theme/oraSurface';
import { humanizeError } from '@/src/utils/errors';

export default function PreparaChiamata() {
  const [frase, setFrase] = useState('');
  const [chi, setChi] = useState('');
  const [prep, setPrep] = useState<MissionPreparation | null>(null);
  const [risposta, setRisposta] = useState('');
  const [altroNumero, setAltroNumero] = useState('');
  const [cambio, setCambio] = useState(false);
  const [inCorso, setInCorso] = useState('');
  const [errore, setErrore] = useState<string | null>(null);
  const [chiamata, setChiamata] = useState('');
  const [inLinea, setInLinea] = useState(false);
  const wide = useBreakpoint() === 'desktop';

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
  const nome = prep?.contact?.name || '';
  const primo = nome.split(/\s+/)[0] || 'questa persona';

  /**
   * Il via libera, che è anche il gesto che compone.
   *
   * Prima prepara (è la porta di sempre: mandato, numero confermato, riassunto),
   * poi compone passando dalla route del prodotto. Il sì è questa pressione,
   * data sul riepilogo che si sta leggendo.
   */
  const chiamaOra = useCallback(() => {
    if (!prep || inCorso) return;
    setInCorso('call');
    setErrore(null);
    api
      .preparationToCall(prep.preparation_id, 'reschedule')
      .then(async (r: { call_id: string; preparation: MissionPreparation }) => {
        setChiamata(r.call_id);
        setPrep(r.preparation);
        await api.placeCall(r.call_id);
        setInLinea(true);
      })
      .catch((e: unknown) => setErrore(humanizeError(e)))
      .finally(() => setInCorso(''));
  }, [prep, inCorso]);

  const corpo = (
    <ScrollView
      style={{ backgroundColor: ora.canvas }}
      contentContainerStyle={[styles.page, wide && styles.pageWide]}
      testID="prepara-chiamata"
    >
      <View style={styles.colonne}>
        <View style={styles.principale}>
          <Text style={[oraType.display, { color: ora.ink }]} accessibilityRole="header">
            Prepariamo la tua telefonata
          </Text>
          <Text style={[oraType.body, { color: ora.ink2, marginTop: 6 }]}>
            ORA si occupa della chiamata per te, in modo sicuro e naturale.
          </Text>

          {!prep ? (
            <OraCard style={styles.blocco}>
              <Text style={[oraType.section, { color: ora.ink }]}>Che cosa devo fare?</Text>
              <TextInput
                value={frase}
                onChangeText={setFrase}
                placeholder="Es. «Chiama Lorenzo e digli di spostare la partita a calcetto»"
                placeholderTextColor={ora.ink3}
                multiline
                testID="prep-request"
                style={[styles.input, styles.inputAlto]}
              />
              <TextInput
                value={chi}
                onChangeText={setChi}
                placeholder="Chi devo chiamare? Es. «Lorenzo»"
                placeholderTextColor={ora.ink3}
                testID="prep-who"
                style={styles.input}
              />
              <OraButton
                label="Preparala"
                testID="prep-start"
                busy={inCorso === 'start'}
                disabled={!frase.trim()}
                onPress={comincia}
              />
            </OraCard>
          ) : null}

          {prep ? (
            <>
              {/* ---- 1 · chi ho trovato, e da dove ---- */}
              <Passo numero={1} titolo="Contatto trovato" sottotitolo={prep.contact ? `Ho trovato ${nome} nella tua rubrica.` : prep.status_label}>
                {prep.contact ? (
                  <View style={styles.contattoRiga} testID="prep-contact">
                    <Avatar name={nome} size={56} />
                    <View style={{ flex: 1 }}>
                      <Text style={[oraType.title, { color: ora.ink }]}>{nome}</Text>
                      <Text style={[oraType.body, { color: ora.ink }]} testID="prep-number">
                        {prep.contact.number}
                      </Text>
                      <Text style={[oraType.small, { color: ora.ink3 }]} testID="prep-source">
                        {prep.contact.source_label}
                        {prep.contact.source_detail ? ` — ${prep.contact.source_detail}` : ''}
                      </Text>
                    </View>
                    {prep.number_confirmed ? (
                      <OraBadge
                        label={prep.number_note || 'Numero verificato'}
                        tone="success"
                        icon="checkmark-circle"
                      />
                    ) : (
                      <OraBadge label="Da confermare" tone="attention" icon="alert-circle-outline" />
                    )}
                  </View>
                ) : null}

                {prep.candidates.length > 1 ? (
                  <View style={styles.blocco} testID="prep-candidates">
                    <Text style={[oraType.body, { color: ora.ink }]}>{prep.says}</Text>
                    {prep.candidates.map((c: PreparationContact) => (
                      <Pressable
                        key={c.number}
                        testID={`prep-candidate-${c.number}`}
                        onPress={() =>
                          void fai('choose', async () =>
                            api.choosePreparationContact(prep.preparation_id, c.number, 'reschedule'),
                          )
                        }
                        style={({ pressed }: any) => [styles.candidato, { opacity: pressed ? 0.7 : 1 }]}
                      >
                        <Text style={[oraType.body, { color: ora.ink, fontWeight: '600' }]}>{c.name}</Text>
                        <Text style={[oraType.body, { color: ora.ink }]}>{c.number}</Text>
                        <Text style={[oraType.small, { color: c.trusted ? ora.success : ora.ink3 }]}>
                          {c.trusted ? '✓ ' : ''}
                          {c.source_label}
                          {c.source_detail ? ` — ${c.source_detail}` : ''}
                        </Text>
                      </Pressable>
                    ))}
                  </View>
                ) : null}

                {prep.other_candidates?.length ? (
                  <View style={styles.blocco} testID="prep-others">
                    <Text style={[oraType.small, { color: ora.ink3 }]}>Altri numeri trovati</Text>
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
                        <Text style={[oraType.small, { color: ora.ink2 }]}>
                          {c.number} · {c.source_label}
                          {c.source_detail ? ` — ${c.source_detail}` : ''}
                        </Text>
                      </Pressable>
                    ))}
                  </View>
                ) : null}

                {puo('confirm_number') ? (
                  <View style={styles.riga}>
                    <OraButton
                      label="Sì, è questo"
                      testID="prep-confirm-yes"
                      busy={inCorso === 'yes'}
                      onPress={() =>
                        void fai('yes', async () =>
                          api.confirmPreparationNumber(prep.preparation_id, true, {
                            operation: 'reschedule',
                          }),
                        )
                      }
                    />
                    <OraButton
                      label="No, non è quello"
                      kind="quiet"
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

                {puo('change_number') && !cambio ? (
                  <View style={styles.riga}>
                    <OraButton
                      label="Cambia numero"
                      kind="quiet"
                      compact
                      testID="prep-change-number"
                      onPress={() => setCambio(true)}
                    />
                    <OraButton
                      label="Questo numero è sbagliato"
                      kind="quiet"
                      compact
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

                {puo('give_number') || cambio ? (
                  <View style={styles.blocco}>
                    <TextInput
                      value={altroNumero}
                      onChangeText={setAltroNumero}
                      placeholder="Scrivi tu il numero da chiamare"
                      placeholderTextColor={ora.ink3}
                      testID="prep-give-number"
                      style={styles.input}
                    />
                    <OraButton
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
              </Passo>

              {/* ---- 2 · che cosa dirò, e che cosa non dirò ---- */}
              <Passo
                numero={2}
                titolo="Privacy e intenti"
                sottotitolo="Per la tua sicurezza, seguirò queste regole:"
              >
                <Regola
                  icona="shield-checkmark-outline"
                  titolo={`Prima mi assicuro di parlare con ${primo}.`}
                  corpo="Verifico che sia davvero lei, senza rivelare il motivo."
                />
                <Regola
                  icona="lock-closed-outline"
                  titolo="Solo dopo dico quello che mi hai chiesto."
                  corpo={
                    prep.message_to_deliver
                      ? `Le dirò: «${prep.message_to_deliver}». Non lo dico a nessun altro.`
                      : 'Resto dentro quello che mi hai chiesto: niente impegni presi al posto tuo.'
                  }
                />
                <Regola
                  icona="people-outline"
                  titolo={`Se non è ${primo}, non dico niente.`}
                  corpo="In caso di dubbio chiudo la chiamata e ti avviso."
                />
              </Passo>

              {/* ---- 3 · quello che manca, o il via libera ---- */}
              {puo('answer') && prep.question ? (
                <Passo numero={3} titolo="Mi manca una cosa" sottotitolo={prep.says}>
                  <TextInput
                    value={risposta}
                    onChangeText={setRisposta}
                    placeholder="Es. «sabato alle 19, al massimo alle 20»"
                    placeholderTextColor={ora.ink3}
                    testID="prep-answer"
                    style={styles.input}
                    onSubmitEditing={() => risposta.trim() && void rispondiOra()}
                  />
                  <OraButton
                    label="Rispondi"
                    testID="prep-send-answer"
                    disabled={!risposta.trim()}
                    busy={inCorso === 'answer'}
                    onPress={() => void rispondiOra()}
                  />
                </Passo>
              ) : (
                <Passo
                  numero={3}
                  titolo="Pronto per chiamare"
                  sottotitolo={prep.ready ? 'Tutto è pronto. Vuoi procedere?' : prep.status_label}
                  badge={prep.ready ? 'Telefonata pronta' : undefined}
                >
                  {prep.summary ? (
                    <View style={styles.riassunto} testID="prep-ready">
                      <IconBubble name="call-outline" size={40} />
                      <Text style={[oraType.body, { color: ora.ink, flex: 1 }]}>{prep.summary}</Text>
                    </View>
                  ) : null}

                  {inLinea ? (
                    <Text style={[oraType.body, { color: ora.success }]} testID="prep-calling">
                      Sto chiamando {primo}… Ti dico com'è andata appena finisce.
                    </Text>
                  ) : puo('call') ? (
                    <View style={styles.riga}>
                      <OraButton
                        label="Chiama ora"
                        icon="call"
                        testID="prep-make-call"
                        busy={inCorso === 'call'}
                        onPress={chiamaOra}
                      />
                      <OraButton
                        label="Ricomincia"
                        kind="secondary"
                        icon="create-outline"
                        testID="prep-reset"
                        onPress={() => {
                          setPrep(null);
                          setChiamata('');
                          setInLinea(false);
                          setFrase('');
                          setChi('');
                        }}
                      />
                    </View>
                  ) : null}

                  {chiamata && !inLinea ? (
                    <Text style={[oraType.small, { color: ora.ink2 }]} testID="prep-call-ready">
                      Chiamata preparata.
                    </Text>
                  ) : null}
                </Passo>
              )}

              {prep.number_rejected ? (
                <Text style={[oraType.small, { color: ora.attention }]} testID="prep-blocked">
                  Non telefono a nessuno finché non mi dici qual è il numero giusto.
                </Text>
              ) : null}

              {errore ? (
                <Text style={[oraType.small, { color: ora.attention }]} testID="prep-error">
                  {errore}
                </Text>
              ) : null}
            </>
          ) : null}
        </View>

        {/* ---- la colonna di destra: la richiesta e il riepilogo ---- */}
        {wide && prep ? (
          <View style={styles.lato}>
            <OraCard style={styles.latoCard}>
              <View style={styles.latoHead}>
                <Ionicons name="chatbubble-ellipses-outline" size={20} color={ora.deep} />
                <Text style={[oraType.section, { color: ora.ink }]}>La tua richiesta</Text>
              </View>
              <View style={styles.bolla}>
                <Text style={[oraType.body, { color: ora.ink }]}>{prep.you_asked}</Text>
              </View>
            </OraCard>

            <OraCard style={styles.latoCard}>
              <View style={styles.latoHead}>
                <Ionicons name="call-outline" size={20} color={ora.deep} />
                <Text style={[oraType.section, { color: ora.ink }]}>Riepilogo chiamata</Text>
              </View>
              {prep.contact ? (
                <VoceLato icona="person-outline" titolo="Destinatario">
                  <Text style={[oraType.body, { color: ora.ink }]}>{nome}</Text>
                  <Text style={[oraType.body, { color: ora.ink }]}>{prep.contact.number}</Text>
                  <Text style={[oraType.small, { color: ora.ink3 }]}>
                    {prep.contact.source_label}
                    {prep.contact.source_detail ? ` — ${prep.contact.source_detail}` : ''}
                  </Text>
                </VoceLato>
              ) : null}
              {prep.message_to_deliver ? (
                <VoceLato icona="chatbox-ellipses-outline" titolo="Messaggio">
                  <Text style={[oraType.body, { color: ora.ink }]}>«{prep.message_to_deliver}»</Text>
                </VoceLato>
              ) : null}
              <VoceLato icona="shield-checkmark-outline" titolo="Sicurezza">
                <Spunta testo={`Verifico che sia ${primo}`} />
                <Spunta testo="Non rivelo il messaggio ad altri" />
                <Spunta testo="Interrompo in caso di dubbio" />
              </VoceLato>
            </OraCard>
          </View>
        ) : null}
      </View>
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

  return <DesktopShell active="chiamate">{corpo}</DesktopShell>;
}

/** Un passo della preparazione: numero, titolo, e quello che c'è dentro. */
function Passo({
  numero,
  titolo,
  sottotitolo,
  badge,
  children,
}: {
  numero: number;
  titolo: string;
  sottotitolo?: string;
  badge?: string;
  children: React.ReactNode;
}) {
  return (
    <View style={styles.passo}>
      <View style={styles.passoNum}>
        <Text style={styles.passoNumText}>{numero}</Text>
      </View>
      <OraCard style={styles.passoCard}>
        <View style={styles.passoHead}>
          <View style={{ flex: 1 }}>
            <Text style={[oraType.section, { color: ora.ink }]}>{titolo}</Text>
            {sottotitolo ? (
              <Text style={[oraType.small, { color: ora.ink2, marginTop: 3 }]}>{sottotitolo}</Text>
            ) : null}
          </View>
          {badge ? <OraBadge label={badge} tone="success" icon="checkmark-circle" /> : null}
        </View>
        {children}
      </OraCard>
    </View>
  );
}

function Regola({ icona, titolo, corpo }: { icona: any; titolo: string; corpo: string }) {
  return (
    <View style={styles.regola}>
      <IconBubble name={icona} size={40} />
      <View style={{ flex: 1 }}>
        <Text style={[oraType.body, { color: ora.ink, fontWeight: '600' }]}>{titolo}</Text>
        <Text style={[oraType.small, { color: ora.ink2, marginTop: 2 }]}>{corpo}</Text>
      </View>
    </View>
  );
}

function VoceLato({ icona, titolo, children }: { icona: any; titolo: string; children: React.ReactNode }) {
  return (
    <View style={styles.voceLato}>
      <IconBubble name={icona} size={36} />
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={[oraType.small, { color: ora.ink3 }]}>{titolo}</Text>
        {children}
      </View>
    </View>
  );
}

function Spunta({ testo }: { testo: string }) {
  return (
    <View style={styles.spunta}>
      <Ionicons name="checkmark-circle" size={16} color={ora.success} />
      <Text style={[oraType.small, { color: ora.ink2 }]}>{testo}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  page: { padding: 24, paddingBottom: 64 },
  pageWide: { padding: 32 },
  colonne: { flexDirection: 'row', gap: 24, alignItems: 'flex-start' },
  principale: { flex: 1, minWidth: 0, gap: 18 },
  lato: { width: 360, gap: 16, paddingTop: 4 },
  latoCard: { gap: 14, padding: 20 },
  latoHead: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  bolla: {
    backgroundColor: ora.surfaceWarm,
    borderRadius: ora.radius.inner,
    padding: 14,
  },
  voceLato: { flexDirection: 'row', gap: 12, alignItems: 'flex-start' },
  spunta: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  passo: { flexDirection: 'row', gap: 16, alignItems: 'flex-start' },
  passoNum: {
    width: 30, height: 30, borderRadius: 15, backgroundColor: ora.cta,
    alignItems: 'center', justifyContent: 'center', marginTop: 16,
  },
  passoNumText: { color: '#FFFFFF', fontSize: 14, fontWeight: '700' },
  passoCard: { flex: 1, gap: 16 },
  passoHead: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  contattoRiga: {
    flexDirection: 'row', alignItems: 'center', gap: 16,
    backgroundColor: ora.surfaceTint, borderRadius: ora.radius.inner, padding: 16,
  },
  regola: { flexDirection: 'row', gap: 14, alignItems: 'flex-start' },
  riassunto: {
    flexDirection: 'row', gap: 14, alignItems: 'center',
    backgroundColor: ora.surfaceTint, borderRadius: ora.radius.inner, padding: 16,
  },
  blocco: { gap: 12 },
  riga: { flexDirection: 'row', gap: 12, flexWrap: 'wrap' },
  candidato: {
    borderWidth: StyleSheet.hairlineWidth, borderColor: ora.hairline,
    borderRadius: ora.radius.inner, padding: 14, gap: 2,
  },
  altro: { paddingVertical: 6 },
  input: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: ora.hairline,
    borderRadius: ora.radius.control,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 15,
    color: ora.ink,
    backgroundColor: ora.surface,
  },
  inputAlto: { minHeight: 88, textAlignVertical: 'top' },
});
