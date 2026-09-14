/**
 * One call, opened.
 *
 * The order is the order of the questions: how did it go, who was called and
 * why, and — only if asked — what was said. The transcript is behind a button
 * because most of the time the one-line outcome is the whole answer, and
 * pouring twenty lines of dialogue onto the page would bury it.
 *
 * The button says "Mostra trascrizione", not "Trascrivi". Nothing is being
 * transcribed when you press it: the text was collected while the call was
 * happening, because both sides produce text anyway, and no recording was
 * ever kept. "Genera" would be a small lie about how this works, and the
 * whole point of not keeping audio is undermined by pretending we could.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';

import {
  api,
  type CallDetail,
  type CallTranscriptEntry,
} from '@/src/api/client';
import { ErrorState } from '@/src/components/ui/ErrorState';
import { Appear, useAmbientInset } from '@/src/shell';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { humanizeError } from '@/src/utils/errors';
import {
  howLong,
  toneColors,
  toneOf,
  whenItHappened,
  whoWasCalled,
} from '@/src/components/calls/callPresentation';

const MAX_WIDTH = 720;

export default function CallDetailScreen() {
  const { colors } = useTheme();
  const ambient = useAmbientInset();
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { width } = useWindowDimensions();
  const padH = width < 380 ? tokens.spacing['16'] : tokens.spacing['24'];

  const [call, setCall] = useState<CallDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [transcript, setTranscript] = useState<CallTranscriptEntry[] | null>(null);
  const [whyEmpty, setWhyEmpty] = useState('');
  const [loadingTranscript, setLoadingTranscript] = useState(false);
  const [transcriptAsked, setTranscriptAsked] = useState(false);

  useEffect(() => {
    let vivo = true;
    (async () => {
      try {
        const res = await api.callDetail(String(id));
        if (vivo) setCall(res.call);
      } catch (e) {
        if (vivo) setError(humanizeError(e));
      } finally {
        if (vivo) setLoading(false);
      }
    })();
    return () => {
      vivo = false;
    };
  }, [id]);

  /**
   * The transcript, when asked for.
   *
   * A call with nothing in it — nobody answered, the line was busy — comes
   * back empty with a reason, not as an error. Not having spoken to anyone is
   * an outcome, not a fault, and the page must not break over it.
   */
  const showTranscript = useCallback(async () => {
    setTranscriptAsked(true);
    setLoadingTranscript(true);
    try {
      const res = await api.callTranscript(String(id));
      setTranscript(res.entries ?? []);
      setWhyEmpty(res.why_empty ?? '');
    } catch (e) {
      setWhyEmpty(humanizeError(e));
      setTranscript([]);
    } finally {
      setLoadingTranscript(false);
    }
  }, [id]);

  const tono = call ? toneOf(call.presentation_status) : 'neutral';
  const pill = toneColors(tono, colors);

  return (
    <SafeAreaView
      edges={['top']}
      style={[styles.safe, { backgroundColor: colors.backgroundPrimary }]}
    >
      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          { paddingHorizontal: padH, paddingBottom: ambient.paddingBottom + 40 },
        ]}
      >
        <View style={[styles.column, { maxWidth: MAX_WIDTH }]}>
          <Pressable
            accessibilityRole="button"
            onPress={() => router.back()}
            hitSlop={12}
          >
            <Text style={[styles.back, { color: colors.textSecondary }]}>
              ← Chiamate
            </Text>
          </Pressable>

          {loading ? (
            <View style={styles.middle}>
              <ActivityIndicator color={colors.textTertiary} />
            </View>
          ) : error || !call ? (
            <ErrorState message={error ?? 'Chiamata non trovata.'} />
          ) : (
            <>
              <Appear>
                <Text style={[styles.who, { color: colors.textPrimary }]}>
                  {whoWasCalled(call)}
                </Text>
                <View style={[styles.pill, { backgroundColor: pill.bg }]}>
                  <Text style={[styles.pillText, { color: pill.fg }]}>
                    {call.status_label}
                  </Text>
                </View>
              </Appear>

              {/* Il risultato sta in alto perché è la domanda che ha portato
                  qualcuno ad aprire questa pagina. */}
              <Appear>
                <View
                  style={[
                    styles.outcomeBox,
                    {
                      backgroundColor: colors.surface,
                      // Una telefonata riuscita che non ha potuto scrivere
                      // niente non può avere il bordo di una cosa a posto:
                      // è esattamente il caso in cui il colore rassicurante
                      // sarebbe la bugia.
                      borderColor:
                        tono === 'attention' || call.changed_something === false
                          ? colors.warning
                          : colors.border,
                    },
                  ]}
                >
                  <Text style={[styles.label, { color: colors.textTertiary }]}>
                    Risultato
                  </Text>
                  <Text style={[styles.outcome, { color: colors.textPrimary }]}>
                    {call.outcome_summary}
                  </Text>

                  {/* Che cosa ORA ha provato a cambiare, quando non c'è
                      riuscita. Il riassunto sopra lo dice già in una riga;
                      questa è la riga in più che serve a chi deve decidere
                      se rifarlo a mano — e dice che cosa si è fermato, non
                      solo che si è fermato. */}
                  {call.changed_something === false && call.application_error ? (
                    <Text
                      testID="call-application-error"
                      style={[styles.aside, { color: colors.textSecondary }]}
                    >
                      {call.application_error.charAt(0).toUpperCase() +
                        call.application_error.slice(1)}
                      .
                    </Text>
                  ) : null}

                  {call.needs_decision ? (
                    <Text
                      accessibilityRole="button"
                      onPress={() => router.push('/(tabs)/ora' as any)}
                      style={[styles.cta, { color: colors.accent }]}
                    >
                      Decidi come procedere
                    </Text>
                  ) : null}
                </View>
              </Appear>

              <Appear>
                <View style={styles.facts}>
                  <Fact label="Motivo" value={call.reason_summary} />
                  <Fact label="Numero" value={call.counterparty_number} />
                  <Fact
                    label="Data e ora"
                    value={whenItHappened(call.started_at || call.created_at)}
                  />
                  <Fact
                    label="Durata"
                    value={howLong(call.duration_seconds) || '—'}
                  />
                  {/* Solo quando c'era qualcosa da cambiare: su una chiamata
                      che doveva solo chiedere, una riga «Calendario: —»
                      inventerebbe un'aspettativa che nessuno aveva. */}
                  {call.changed_something !== null ? (
                    <Fact
                      label="Calendario"
                      value={
                        call.changed_something ? 'Aggiornato' : 'Non aggiornato'
                      }
                    />
                  ) : null}
                </View>
              </Appear>

              <Appear>
                <View
                  style={[styles.divider, { backgroundColor: colors.divider }]}
                />
                <Text style={[styles.section, { color: colors.textPrimary }]}>
                  Trascrizione
                </Text>

                {!transcriptAsked ? (
                  <>
                    <Pressable
                      accessibilityRole="button"
                      onPress={showTranscript}
                      style={({ pressed }) => [
                        styles.button,
                        {
                          borderColor: colors.border,
                          backgroundColor: colors.surface,
                        },
                        pressed && { opacity: 0.7 },
                      ]}
                    >
                      <Text
                        style={[styles.buttonText, { color: colors.textPrimary }]}
                      >
                        Mostra trascrizione
                      </Text>
                    </Pressable>
                    <Text style={[styles.note, { color: colors.textTertiary }]}>
                      Di questa chiamata è rimasto solo il testo. Nessuna
                      registrazione è stata conservata.
                    </Text>
                  </>
                ) : loadingTranscript ? (
                  <ActivityIndicator color={colors.textTertiary} />
                ) : (transcript?.length ?? 0) === 0 ? (
                  <Text style={[styles.note, { color: colors.textSecondary }]}>
                    {whyEmpty || 'Non è rimasto nulla da leggere.'}
                  </Text>
                ) : (
                  <View style={styles.transcript}>
                    {transcript!.map((riga) => (
                      <View key={riga.sequence_number} style={styles.line}>
                        <Text
                          style={[
                            styles.speaker,
                            {
                              color:
                                riga.speaker === 'ora'
                                  ? colors.accent
                                  : colors.textTertiary,
                            },
                          ]}
                        >
                          {riga.speaker === 'ora'
                            ? 'ORA'
                            : whoWasCalled(call)}
                        </Text>
                        <Text
                          style={[styles.said, { color: colors.textPrimary }]}
                        >
                          {riga.text}
                        </Text>
                      </View>
                    ))}
                  </View>
                )}
              </Appear>
            </>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  const { colors } = useTheme();
  if (!value) return null;
  return (
    <View style={styles.fact}>
      <Text style={[styles.label, { color: colors.textTertiary }]}>{label}</Text>
      <Text style={[styles.factValue, { color: colors.textPrimary }]}>
        {value}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  scroll: { paddingTop: tokens.spacing['16'], alignItems: 'center' },
  column: { width: '100%', gap: tokens.spacing['20'] },
  back: { fontSize: 15, fontWeight: '500' },
  who: { fontSize: 26, fontWeight: '700', letterSpacing: -0.5 },
  pill: {
    alignSelf: 'flex-start',
    marginTop: tokens.spacing['8'],
    paddingHorizontal: tokens.spacing['8'],
    paddingVertical: 3,
    borderRadius: tokens.radius.pill,
  },
  pillText: { fontSize: 11, fontWeight: '600', letterSpacing: 0.2 },
  outcomeBox: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.lg,
    padding: tokens.spacing['16'],
    gap: tokens.spacing['4'],
  },
  outcome: { fontSize: 17, lineHeight: 24, fontWeight: '500' },
  aside: { fontSize: 14, lineHeight: 20, marginTop: tokens.spacing['8'] },
  cta: { fontSize: 15, fontWeight: '600', marginTop: tokens.spacing['12'] },
  facts: { gap: tokens.spacing['16'] },
  fact: { gap: 2 },
  label: { fontSize: 12, fontWeight: '600', letterSpacing: 0.3 },
  factValue: { fontSize: 15, lineHeight: 21 },
  divider: { height: StyleSheet.hairlineWidth, marginBottom: tokens.spacing['16'] },
  section: { fontSize: 18, fontWeight: '700', letterSpacing: -0.3 },
  button: {
    marginTop: tokens.spacing['12'],
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.md,
    paddingVertical: tokens.spacing['12'],
    alignItems: 'center',
  },
  buttonText: { fontSize: 15, fontWeight: '600' },
  note: { fontSize: 13, lineHeight: 19, marginTop: tokens.spacing['8'] },
  middle: { paddingVertical: tokens.spacing['48'], alignItems: 'center' },
  transcript: { gap: tokens.spacing['16'], marginTop: tokens.spacing['16'] },
  line: { gap: 3 },
  speaker: { fontSize: 11, fontWeight: '700', letterSpacing: 0.4 },
  said: { fontSize: 15, lineHeight: 22 },
});
