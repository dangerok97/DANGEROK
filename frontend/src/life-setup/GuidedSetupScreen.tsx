/**
 * The guided first setup.
 *
 * A person arriving for the first time should see, immediately, that ORA wants
 * to understand the separate parts of their life — and should be able to get
 * through it by choosing, never by composing sentences at a chat box. The free
 * conversation is ORA's, afterwards; this is a guided path with a visible
 * shape: where you are, what is being asked, what comes next, and the fact that
 * you can leave at any point.
 *
 * The screen decides nothing. The server sends one area, one objective, the
 * control to draw it with and the options that exist; every branch — what a
 * "no" closes, when an area is finished, which area follows — lives there,
 * because a branch implemented in a component is a branch nobody can test.
 *
 * Layout follows the approved design: the path on the left of the card, the
 * question in the middle, every area and its state on the right, and the
 * profile figure above. On a phone the same pieces stack in the same order.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

import { api, GuidedObjective, GuidedSetupState, type LifeMapResponse } from '@/src/api/client';
import { areaIconName } from '@/src/components/life-profile/areaIcon';
import { requestDevicePosition } from '@/src/life-setup/devicePosition';
import * as DocumentPicker from 'expo-document-picker';
import { useTheme } from '@/src/theme/ThemeProvider';
import { DesktopShell } from '@/src/shell';
import { OraBadge, OraCard } from '@/src/components/ora-ui';
import { ora, oraType } from '@/src/theme/oraSurface';
import { tokens } from '@/src/theme/tokens';
import { humanizeError } from '@/src/utils/errors';

const TWO_COLUMN_AT = 1000;
const RAIL = 360;

/**
 * Lo stato di un'area, detto come lo direbbe una persona.
 *
 *     SELEZIONATA NON VUOL DIRE «IN CORSO».
 *
 * Misurato in app (V3.21.3d): Famiglia al 100%, cliccata, diceva «In corso» —
 * perché la prima riga qui era `if (area.current) return 'In corso'`. Un
 * clic non cambia quello che ORA sa: cambia solo dove stai guardando. Da qui
 * passa soltanto lo stato reale, e «In corso» lo dice il backend quando c'è
 * davvero una domanda aperta.
 */
function stateLabel(area: {
  state: string;
  state_label: string;
  percent: number;
  in_progress?: boolean;
  skipped?: boolean;
}) {
  if (area.percent >= 100) return 'Conosciuta';
  if (area.in_progress) return 'In corso';
  if (area.skipped) return 'Saltata';
  return area.state_label;
}

function Bar({ percent, color, track }: { percent: number; color: string; track: string }) {
  const width = `${Math.max(0, Math.min(100, percent))}%` as const;
  return (
    <View style={[styles.track, { backgroundColor: track }]}>
      <View style={[styles.fill, { width, backgroundColor: color }]} />
    </View>
  );
}

export function GuidedSetupScreen() {
  const { colors } = useTheme();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const twoColumn = width >= TWO_COLUMN_AT;

  const [state, setState] = useState<GuidedSetupState | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // What the person has picked but not yet sent. Cleared on every new question.
  const [picked, setPicked] = useState<string[]>([]);
  const [typed, setTyped] = useState('');
  const [otherOpen, setOtherOpen] = useState(false);
  // Asking the device where it is, and what came back: a town, never
  // coordinates.
  const [locating, setLocating] = useState(false);
  const [locationNote, setLocationNote] = useState<string | null>(null);
  // The document step, which is an action and not a field.
  const [docState, setDocState] = useState<{
    phase: 'idle' | 'picking' | 'uploading' | 'working' | 'failed';
    name?: string;
    message?: string;
  }>({ phase: 'idle' });

  /*
    Guardare un'area e rispondere a un'area sono due cose diverse.

        LA REFERENCE MOSTRA PRIMA IL RIEPILOGO, POI LA DOMANDA.

    Chi clicca «Studio» dalla colonna vuole vedere che cosa ORA sa e che cosa
    le manca; è quando preme «Continua con Studio» che vuole rispondere. Al
    primo giro invece si va dritti alla domanda: non c'è ancora niente da
    riepilogare.
  */
  const [percheAperto, setPercheAperto] = useState(false);

  const objective = state?.objective ?? null;
  const areas = state?.areas ?? [];
  const current = areas.find((a) => a.area_id === state?.current_area_id) || null;
  const primoGiro = !!state && !state.finished;
  const mostraDomanda = !!objective && (primoGiro || !!current?.in_progress);

  /*
    Le situazioni in corso arrivano dalla mappa della vita — la stessa che
    alimentava la vecchia pagina dei contesti. Nessun dato è stato buttato: ha
    cambiato posto, ed è diventato una sezione invece di una schermata.
  */
  const [situations, setSituations] = useState<LifeMapResponse['situations']>([]);

  const load = useCallback(async () => {
    try {
      const res = await api.guidedSetupState();
      setState(res);
      setError(null);
      try {
        const mappa = await api.getLifeMap();
        setSituations(mappa.situations || []);
      } catch {
        // Le situazioni sono un di più: se non arrivano, la pagina resta
        // quella che serve — il profilo e quello che manca.
      }
    } catch (e) {
      setError(humanizeError(e, 'default'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const reset = useCallback(() => {
    setPicked([]);
    setTyped('');
    setOtherOpen(false);
    setLocationNote(null);
    setDocState({ phase: 'idle' });
  }, []);

  const send = useCallback(
    async (body: Parameters<typeof api.guidedSetupAnswer>[0]) => {
      if (busy) return;
      setBusy(true);
      try {
        const res = await api.guidedSetupAnswer(body);
        setState(res);
        reset();
        setError(null);
      } catch (e) {
        setError(humanizeError(e, 'default'));
      } finally {
        setBusy(false);
      }
    },
    [busy, reset],
  );

  /*
    "Usa la mia posizione".

    The browser's own prompt is the permission flow — there is no second
    consent screen to build — and the coordinates never surface: they go to the
    reverse geocoder and a town comes back, which is what somebody setting up
    their home should read, and correct if it is wrong.
  */
  const useMyLocation = useCallback(async () => {
    if (locating) return;
    setLocating(true);
    setLocationNote(null);
    try {
      const pos = await requestDevicePosition();
      if (!pos) {
        setLocationNote('Non sono riuscita a rilevarla. Puoi scriverla qui sotto.');
        return;
      }
      const res = await api.lifeSetupReverseGeocode(pos.lat, pos.lon);
      const city = (res?.city || '').trim();
      if (!city) {
        setLocationNote('Non sono riuscita a rilevarla. Puoi scriverla qui sotto.');
        return;
      }
      setTyped(city);
      setLocationNote('Rilevata dalla tua posizione. Puoi correggerla.');
    } catch {
      setLocationNote('Non sono riuscita a rilevarla. Puoi scriverla qui sotto.');
    } finally {
      setLocating(false);
    }
  }, [locating]);

  /*
    The document step, through the pipeline that already exists.

    Upload, attach, and then the person carries on: reading a document takes as
    long as it takes, and nobody should sit watching a spinner in the middle of
    a first setup. "Più tardi" is always there, and it is an answer rather than
    a failure.
  */
  const uploadDocument = useCallback(async () => {
    if (!objective || docState.phase === 'uploading') return;
    let file: DocumentPicker.DocumentPickerAsset | null = null;
    setDocState({ phase: 'picking' });
    try {
      const res = await DocumentPicker.getDocumentAsync({
        multiple: false,
        copyToCacheDirectory: true,
        type: ['application/pdf', 'text/plain', 'image/*'],
      });
      if (res.canceled || !res.assets?.[0]) {
        setDocState({ phase: 'idle' });
        return;
      }
      file = res.assets[0];
    } catch (e) {
      setDocState({ phase: 'failed', message: humanizeError(e, 'default') });
      return;
    }

    setDocState({ phase: 'uploading', name: file.name });
    try {
      const up = await api.documentUpload({
        uri: file.uri,
        name: file.name || 'documento.pdf',
        type: file.mimeType || 'application/octet-stream',
      });
      const id = up.document?.id;
      if (!id) throw new Error('Caricamento non riuscito');
      await api.lifeSetupAttachDocument(id, objective.document_type || undefined);
      setDocState({
        phase: 'working',
        name: file.name,
        message: 'Sto leggendo il documento. Puoi andare avanti.',
      });
      void send({ objective_id: objective.id, value: id });
    } catch (e) {
      setDocState({ phase: 'failed', message: humanizeError(e, 'default') });
    }
  }, [docState.phase, objective, send]);

  const submit = useCallback(() => {
    if (!objective) return;
    if (otherOpen) {
      if (!typed.trim()) return;
      void send({ objective_id: objective.id, other_text: typed.trim() });
      return;
    }
    if (['currency', 'number', 'date', 'location', 'text'].includes(objective.control)) {
      if (!typed.trim()) return;
      void send({ objective_id: objective.id, value: typed.trim() });
      return;
    }
    if (!picked.length) return;
    void send({ objective_id: objective.id, option_ids: picked });
  }, [objective, otherOpen, picked, send, typed]);

  const canSubmit = useMemo(() => {
    if (!objective) return false;
    if (otherOpen) return !!typed.trim();
    // The document step never blocks the path: the way on is the upload or
    // “Più tardi”, never a field somebody has to guess at.
    if (objective.control === 'document_upload') return false;
    if (['currency', 'number', 'date', 'location', 'text'].includes(objective.control)) {
      return !!typed.trim();
    }
    return picked.length > 0;
  }, [objective, otherOpen, picked, typed]);

  const leave = useCallback(async () => {
    try {
      await api.guidedSetupFinish();
    } catch {
      // Leaving is the person's decision; it never fails on them.
    }
    router.replace('/');
  }, [router]);

  /*
    «Lo faccio più tardi».

    Non è un abbandono e non è una risposta: è la persona che smette adesso.
    Non si scrive niente — quello che c'è resta dov'è — e si torna alla Home;
    il prossimo ingresso riparte dallo stesso punto, perché il punto è salvato
    nella sessione, non in questa schermata.
  */
  const later = useCallback(() => {
    router.replace('/');
  }, [router]);

  const goNextArea = useCallback(
    async (areaId: string, ref?: string, startQuestion = false) => {
      setBusy(true);
      try {
        setState(await api.guidedSetupGoToArea(areaId, ref, startQuestion));
        reset();
      } catch (e) {
        setError(humanizeError(e, 'default'));
      } finally {
        setBusy(false);
      }
    },
    [reset],
  );

  /*
    «Riprendi da Casa» vuol dire aprire la prima cosa che manca a Casa.

    L'indirizzo portava già `?area=casa`, ma era un parametro decorativo: la
    schermata si apriva dove le pareva. Adesso è il punto in cui si torna, e ci
    si torna una volta sola — dopo, la persona è libera di muoversi.
  */
  const params = useLocalSearchParams<{ area?: string; resume?: string }>();
  const [ripreso, setRipreso] = useState(false);
  useEffect(() => {
    const voluta = String(params.area || '').trim();
    if (!voluta || ripreso || loading || !state) return;
    setRipreso(true);
    if (state.current_area_id !== voluta || !state.objective) {
      void goNextArea(voluta);
    }
  }, [params.area, ripreso, loading, state, goNextArea]);

  const skipArea = useCallback(async () => {
    if (!state?.current_area_id) return;
    setBusy(true);
    try {
      setState(await api.guidedSetupSkipArea(state.current_area_id));
      reset();
    } catch (e) {
      setError(humanizeError(e, 'default'));
    } finally {
      setBusy(false);
    }
  }, [reset, state?.current_area_id]);

  if (loading) {
    return (
      <SafeAreaView style={[styles.root, { backgroundColor: colors.backgroundPrimary }]}>
        <ActivityIndicator color={colors.accent} />
      </SafeAreaView>
    );
  }

  const percent = state?.percent ?? 0;

  // ---- pieces -------------------------------------------------------------

  const header = (
    <View style={styles.header}>
      <Pressable
        onPress={() => router.back()}
        accessibilityRole="button"
        accessibilityLabel="Indietro"
        style={styles.back}
        testID="guided-back"
      >
        <Text style={[styles.backText, { color: colors.textSecondary }]}>← Indietro</Text>
      </Pressable>
      {/*
        Sembrava un bottone e non lo era: una domanda scritta dentro un bordo,
        che non si poteva premere. Adesso si apre, e quello che dice è vero —
        a che cosa servono le risposte, e che restano tue.
      */}
      <Pressable
        onPress={() => setPercheAperto((v) => !v)}
        accessibilityRole="button"
        accessibilityState={{ expanded: percheAperto }}
        style={({ pressed }: any) => [
          styles.why,
          { borderColor: colors.border, backgroundColor: colors.surface },
          pressed && { opacity: 0.7 },
        ]}
        testID="guided-why"
      >
        <Text style={[styles.whyText, { color: colors.textSecondary }]}>
          Perché queste domande?
        </Text>
      </Pressable>
    </View>
  );

  const perche = percheAperto ? (
    <View
      style={[styles.perche, { backgroundColor: ora.surfaceTint, marginTop: 12 }]}
      testID="guided-why-text"
    >
      <Ionicons name="information-circle-outline" size={18} color={ora.deep} />
      <View style={{ flex: 1, gap: 6 }}>
        <Text style={[oraType.small, { color: ora.ink2 }]}>
          ORA usa quello che le dici per ricordarti le cose al momento giusto e per
          non chiedertele due volte. Niente di tutto questo esce da qui, e da Vita
          puoi correggere o togliere quello che vuoi, quando vuoi.
        </Text>
        {current?.purpose ? (
          <Text style={[oraType.small, { color: ora.ink2 }]}>
            Di {current.title.toLowerCase()}: {current.purpose.charAt(0).toLowerCase()}
            {current.purpose.slice(1)}
          </Text>
        ) : null}
      </View>
    </View>
  ) : null;

  const intro = (
    <View style={styles.introRiga}>
      <View style={styles.intro}>
        <Text style={[styles.title, { color: colors.textPrimary }]} testID="guided-title">
          Conosciamoci
        </Text>
        <Text style={[styles.introText, { color: colors.textSecondary }]}>
          ORA vuole conoscere le diverse parti della tua vita{'\n'}
          per aiutarti davvero ogni giorno.
        </Text>
        <Text style={[styles.introText, { color: colors.textSecondary }]}>
          Compiliamo un'area alla volta. Puoi saltare o tornare quando vuoi.
        </Text>
      </View>
      {/*
        La testata editoriale della reference: la frase come nota scritta a
        mano e, accanto, la scena — pianta, libri, portapenne, lampada.

        L'immagine è un asset locale e versionato: `vita-header.png`, che
        `scripts/make-vita-header.py` ritaglia dalla reference approvata —
        disegnarla non funzionava, perché quella è una fotografia. Niente URL
        remoti. La frase resta interfaccia e non entra nel file, così si
        corregge senza rifare un'immagine.
      */}
      {twoColumn ? (
        <View style={styles.testata}>
          <Text style={[styles.nota, { color: ora.deep }]} testID="guided-nota">
            Un quadro più completo,{'\n'}una vita più semplice.
          </Text>
          <Image
            source={require('@/assets/images/vita-header.png')}
            style={styles.testataFoto}
            resizeMode="cover"
            accessibilityIgnoresInvertColors
            accessible
            accessibilityLabel="Una pianta, un portapenne, dei libri e una lampada su una mensola"
            testID="guided-header-image"
          />
        </View>
      ) : null}
    </View>
  );

  const profileCard = (
    <View
      style={[styles.profile, { borderColor: colors.border, backgroundColor: colors.surface }]}
      testID="guided-profile"
    >
      <View style={styles.profileHead}>
        <View style={{ flex: 1 }}>
          <Text style={[styles.profileTitle, { color: ora.ink3 }]}>PROFILO VITA</Text>
          <Text style={[oraType.hero, { color: ora.ink, marginTop: 4 }]}>
            {percent >= 70
              ? 'ORA ha già una buona base per aiutarti.'
              : 'Stiamo costruendo il quadro della tua vita.'}
          </Text>
          <Text style={[oraType.body, { color: ora.ink2, marginTop: 6 }]}>
            Conosce il {percent}% di ciò che può aiutarti. Aggiungi il resto quando vuoi, da Vita.
          </Text>
        </View>
        <Text style={[styles.profilePercent, { color: ora.ink }]} testID="guided-percent">
          {percent}%
        </Text>
      </View>
      <Bar percent={percent} color={ora.cta} track={colors.divider} />
      <Text style={[styles.profileNote, { color: ora.ink3 }]}>
        Più informazioni condividi, più i suggerimenti saranno utili e personalizzati.
      </Text>
    </View>
  );

  const path = (
    <View style={styles.path} testID="guided-path">
      <Text style={[styles.pathTitle, { color: ora.ink3 }]}>PERCORSO</Text>
      {areas.map((a, i) => {
        const isCurrent = a.area_id === state?.current_area_id;
        return (
          /*
            Scegliere un'area dal percorso è il modo più ovvio di muoversi in
            questa pagina, e finora era l'unico che non si poteva fare: le
            righe erano disegni. Adesso aprono l'area, nel pannello centrale.
          */
          <Pressable
            key={a.area_id}
            onPress={() => void goNextArea(a.area_id)}
            accessibilityRole="button"
            accessibilityLabel={`Apri ${a.title}`}
            accessibilityState={{ selected: isCurrent }}
            style={({ pressed }: any) => [
              styles.pathRow,
              isCurrent && { backgroundColor: colors.accentMuted },
              pressed && { opacity: 0.7 },
            ]}
            testID={`guided-path-${a.area_id}`}
          >
            <Text style={[styles.pathNum, { color: colors.textTertiary }]}>{i + 1}</Text>
            <View
              style={[
                styles.pathTile,
                {
                  backgroundColor: isCurrent ? colors.accent : colors.surfaceElevated,
                },
              ]}
            >
              <Ionicons
                name={areaIconName(a.icon_key)}
                size={15}
                color={isCurrent ? colors.onAccent : colors.textTertiary}
              />
            </View>
            <Text
              style={[
                styles.pathLabel,
                { color: isCurrent ? colors.textPrimary : colors.textSecondary },
              ]}
              numberOfLines={1}
            >
              {a.title}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );

  const transition = state?.transition ? (
    <View
      style={[styles.transition, { borderColor: colors.border, backgroundColor: colors.surface }]}
      testID="guided-transition"
    >
      <Text style={[styles.transitionTitle, { color: colors.textPrimary }]}>
        {state.transition.from_title} — {state.transition.from_state_label.toLowerCase()}
      </Text>
      <Text style={[styles.transitionNote, { color: colors.textSecondary }]}>
        ORA ne conosce il {state.transition.from_percent}%. Possiamo completare il resto più
        avanti.
      </Text>
      <Pressable
        onPress={() => void goNextArea(state.transition!.to_area_id)}
        accessibilityRole="button"
        style={[styles.primary, { backgroundColor: colors.accent }]}
        testID="guided-go-next-area"
      >
        <Text style={[styles.primaryText, { color: colors.onAccent }]}>
          Passa a {state.transition.to_title}
        </Text>
      </Pressable>
    </View>
  ) : null;

  const question = objective ? (
    <View style={styles.question} testID="guided-question">
      <Text style={[styles.questionText, { color: colors.textPrimary }]}>{objective.question}</Text>
      {objective.hint ? (
        <Text style={[styles.questionHint, { color: colors.textSecondary }]}>{objective.hint}</Text>
      ) : null}

      {objective.options.length && !otherOpen ? (
        <View style={styles.options} testID="guided-options">
          {objective.options.map((o) => {
            const on = picked.includes(o.id);
            return (
              <Pressable
                key={o.id}
                onPress={() =>
                  setPicked((prev) =>
                    objective.control === 'multi'
                      ? prev.includes(o.id)
                        ? prev.filter((x) => x !== o.id)
                        : [...prev, o.id]
                      : [o.id],
                  )
                }
                accessibilityRole={objective.control === 'multi' ? 'checkbox' : 'radio'}
                accessibilityState={{ checked: on }}
                accessibilityLabel={o.label}
                style={[
                  styles.option,
                  {
                    borderColor: on ? colors.accent : colors.border,
                    backgroundColor: on ? colors.accentMuted : colors.surface,
                  },
                ]}
                testID={`guided-option-${o.id}`}
              >
                <Text style={[styles.optionLabel, { color: colors.textPrimary }]}>
                  {o.label}
                </Text>
                {o.description ? (
                  <Text style={[styles.optionDesc, { color: colors.textTertiary }]}>
                    {o.description}
                  </Text>
                ) : null}
              </Pressable>
            );
          })}
          {objective.allow_other ? (
            <Pressable
              onPress={() => {
                setOtherOpen(true);
                setPicked([]);
              }}
              accessibilityRole="button"
              accessibilityLabel="Altro"
              style={[styles.option, { borderColor: colors.border, backgroundColor: colors.surface }]}
              testID="guided-option-altro"
            >
              <Text style={[styles.optionLabel, { color: colors.textPrimary }]}>Altro</Text>
            </Pressable>
          ) : null}
        </View>
      ) : null}

      {/*
        "Altro" opens a small box for this question only. It is the one place
        free text exists in the first setup, and it never turns into a general
        conversation with ORA — that belongs to ORA proper, afterwards.
      */}
      {otherOpen ? (
        <View style={styles.otherBox} testID="guided-other">
          <Text style={[styles.questionHint, { color: colors.textSecondary }]}>
            Descrivi brevemente la tua situazione
          </Text>
          <TextInput
            value={typed}
            onChangeText={setTyped}
            placeholder="La tua risposta"
            placeholderTextColor={colors.placeholder}
            style={[
              styles.input,
              { borderColor: colors.border, color: colors.textPrimary, backgroundColor: colors.surface },
            ]}
            testID="guided-other-input"
            autoFocus
          />
          <Pressable onPress={() => { setOtherOpen(false); setTyped(''); }} style={styles.linkRow}>
            <Text style={[styles.link, { color: colors.accent }]}>Torna alle opzioni</Text>
          </Pressable>
        </View>
      ) : null}

      {/*
        A document is handed over, not typed. A text field here was a dead end:
        nothing to write, and no way forward.
      */}
      {objective.control === 'document_upload' && !otherOpen ? (
        <View style={styles.docBox} testID="guided-document">
          <Pressable
            onPress={() => void uploadDocument()}
            disabled={docState.phase === 'uploading'}
            accessibilityRole="button"
            accessibilityLabel="Carica documento"
            style={[
              styles.uploadBtn,
              { borderColor: colors.accent, backgroundColor: colors.accentMuted },
              docState.phase === 'uploading' && { opacity: 0.6 },
            ]}
            testID="guided-upload"
          >
            <Ionicons name="attach-outline" size={18} color={colors.accent} />
            <Text style={[styles.uploadText, { color: colors.accent }]}>
              {docState.phase === 'uploading' ? 'Carico…' : 'Carica documento'}
            </Text>
          </Pressable>
          {docState.name || docState.message ? (
            <Text
              style={[styles.questionHint, { color: colors.textSecondary }]}
              testID="guided-doc-state"
            >
              {docState.phase === 'failed'
                ? docState.message
                : `${docState.name || 'Documento'} — ${docState.message || 'selezionato'}`}
            </Text>
          ) : null}
        </View>
      ) : null}

      {objective.control === 'location' && !otherOpen ? (
        <View style={styles.docBox} testID="guided-location">
          <Pressable
            onPress={() => void useMyLocation()}
            disabled={locating}
            accessibilityRole="button"
            accessibilityLabel="Usa la mia posizione"
            style={[
              styles.uploadBtn,
              { borderColor: colors.accent, backgroundColor: colors.accentMuted },
              locating && { opacity: 0.6 },
            ]}
            testID="guided-use-location"
          >
            <Ionicons name="location-outline" size={18} color={colors.accent} />
            <Text style={[styles.uploadText, { color: colors.accent }]}>
              {locating ? 'Cerco la posizione…' : 'Usa la mia posizione'}
            </Text>
          </Pressable>
          {locationNote ? (
            <Text
              style={[styles.questionHint, { color: colors.textSecondary }]}
              testID="guided-location-note"
            >
              {locationNote}
            </Text>
          ) : null}
        </View>
      ) : null}

      {!objective.options.length && !otherOpen && objective.control !== 'document_upload' ? (
        <View style={styles.otherBox}>
          <TextInput
            value={typed}
            onChangeText={setTyped}
            placeholder={
              objective.control === 'currency'
                ? `Importo ${objective.unit}`.trim()
                : objective.control === 'date'
                  ? 'gg/mm/aaaa'
                  : objective.control === 'location'
                    ? 'Comune'
                    : 'La tua risposta'
            }
            placeholderTextColor={colors.placeholder}
            keyboardType={
              objective.control === 'currency' || objective.control === 'number'
                ? 'numeric'
                : 'default'
            }
            style={[
              styles.input,
              { borderColor: colors.border, color: colors.textPrimary, backgroundColor: colors.surface },
            ]}
            testID={`guided-input-${objective.control}`}
          />
        </View>
      ) : null}

      <View style={[styles.privacy, { backgroundColor: colors.surfaceElevated }]}>
        <Text style={[styles.privacyText, { color: colors.textSecondary }]}>
          I tuoi dati sono al sicuro con ORA. Puoi modificarli o rimuoverli in qualsiasi momento
          da Vita.
        </Text>
      </View>

      <View style={styles.actions}>
        <Pressable
          onPress={() => void skipArea()}
          accessibilityRole="button"
          style={[styles.secondary, { borderColor: colors.border }]}
          testID="guided-skip-area"
        >
          <Text style={[styles.secondaryText, { color: colors.textSecondary }]}>
            Salta questa area
          </Text>
        </Pressable>
        <View style={styles.actionsRight}>
          {objective.allow_decline ? (
            <Pressable
              onPress={() => void send({ objective_id: objective.id, action: 'decline' })}
              accessibilityRole="button"
              style={styles.linkRow}
              testID="guided-decline"
            >
              <Text style={[styles.link, { color: colors.textTertiary }]}>
                Preferisco non indicarlo
              </Text>
            </Pressable>
          ) : null}
          {objective.allow_skip ? (
            <Pressable
              onPress={() => void send({ objective_id: objective.id, action: 'skip' })}
              accessibilityRole="button"
              style={styles.linkRow}
              testID="guided-skip-question"
            >
              <Text style={[styles.link, { color: colors.textTertiary }]}>Più tardi</Text>
            </Pressable>
          ) : null}
          {objective.control === 'document_upload' ? null : (
          <Pressable
            onPress={submit}
            disabled={!canSubmit || busy}
            accessibilityRole="button"
            accessibilityState={{ disabled: !canSubmit || busy }}
            style={[
              styles.primary,
              { backgroundColor: colors.accent },
              (!canSubmit || busy) && { opacity: 0.45 },
            ]}
            testID="guided-next"
          >
            <Text style={[styles.primaryText, { color: colors.onAccent }]}>Avanti</Text>
          </Pressable>
          )}
        </View>
      </View>
    </View>
  ) : null;

  /*
    Dove conviene andare dopo.

        «CASA È QUASI COMPLETA» DEVE ESSERE VERO.

    Prima questa riga diceva: la prima area della lista che non sia piena. Cioè
    l'ordine del menu travestito da consiglio — e la frase che lo accompagnava
    poteva essere semplicemente falsa. La graduatoria adesso la fa il backend
    (`recommend.next_recommended_area`), che manda anche il motivo: qui si
    mostra la frase, nei test si controlla il codice.
  */
  const consiglio = state?.recommended || null;

  /*
        LA STESSA COSA, DETTA DUE VOLTE, NON È IL DOPPIO DI INFORMAZIONE.

    Qui stava un riepilogo globale — «ORA ha un buon punto di partenza»,
    la percentuale, «Prossimo passo consigliato», «Completa Casa» — dentro il
    pannello di un'area. Ma quella percentuale è già scritta in grande in
    «Profilo Vita», due centimetri più su, e un secondo posto dove leggerla è
    solo un secondo posto dove può diventare diversa.

    Il pannello adesso risponde a una domanda per volta, in quest'ordine:
    cosa ORA sa di quest'area · cosa le manca · come sta quest'area · e solo
    alla fine, staccata, dove conviene andare dopo.
  */

  const areaCard = (
    <View
      style={[styles.card, { borderColor: colors.border, backgroundColor: colors.surface }]}
      testID="guided-card"
    >
      {twoColumn ? <View style={styles.cardPath}>{path}</View> : null}
      <View style={styles.cardBody}>
        {current ? (
          <View style={styles.cardHead}>
            <View style={[styles.headTile, { backgroundColor: colors.accentMuted }]}>
              <Ionicons
                name={areaIconName(current.icon_key)}
                size={19}
                color={colors.accent}
              />
            </View>
            <Text style={[styles.cardTitle, { color: colors.textPrimary }]} testID="guided-current-area">
              {areas.findIndex((a) => a.area_id === current.area_id) + 1}. {current.title}
            </Text>
            {/*
              Lo stato vero dell'area, non «In corso» scritto a mano: questo
              chip stava sotto il titolo di un'area completa e la smentiva.
            */}
            <View style={[styles.chip, { backgroundColor: colors.accentMuted }]}>
              <Text
                style={[styles.chipText, { color: colors.accent }]}
                testID="guided-current-state"
              >
                {stateLabel(current)}
              </Text>
            </View>
          </View>
        ) : null}
        {current ? (
          <Text style={[styles.cardSub, { color: ora.ink2 }]}>{current.description}</Text>
        ) : null}
        {/*
          A che cosa serve saperlo, come nella reference. Non è una rassicurazione
          generica: ogni area dice la sua, e chi legge può decidere se gli va.
        */}
        {current?.purpose ? (
          <View style={[styles.perche, { backgroundColor: ora.surfaceTint }]} testID="guided-purpose">
            <Ionicons name="information-circle-outline" size={18} color={ora.deep} />
            <Text style={[oraType.small, { color: ora.ink2, flex: 1 }]}>{current.purpose}</Text>
          </View>
        ) : null}
        {current ? (
          <View style={styles.sapere}>
            {/*
              Quello che ORA sa e quello che le manca, dai conteggi canonici:
              nessun elenco inventato, e se non c'è niente la riga non c'è.
            */}
            {current.known_count > 0 ? (
              <View style={styles.sapereBlocco}>
                <View style={styles.sapereHead}>
                  <Ionicons name="checkmark-circle" size={18} color={ora.success} />
                  <Text style={[oraType.body, { color: ora.ink, fontWeight: '600', flex: 1 }]}>
                    Quello che ORA sa già
                  </Text>
                  {/*
                    «Modifica», come nella reference: riapre la prima cosa che
                    ORA sa di quest'area e la richiede. La risposta riscrive lo
                    stesso riferimento — nessuna seconda copia del fatto, e
                    niente da riconciliare dopo.
                  */}
                  {(current.known || []).length ? (
                    <Pressable
                      onPress={() =>
                        void goNextArea(current.area_id, (current.known || [])[0].source_ref
                          || (current.known || [])[0].ref)
                      }
                      accessibilityRole="button"
                      accessibilityLabel={`Modifica quello che ORA sa di ${current.title}`}
                      style={({ pressed }: any) => [pressed && { opacity: 0.6 }]}
                      testID="guided-edit-known"
                    >
                      <Text style={[oraType.small, { color: ora.cta, fontWeight: '600' }]}>
                        Modifica
                      </Text>
                    </Pressable>
                  ) : null}
                </View>
                {/*
                  I fatti, non il conteggio: «Corso di laurea: Ingegneria
                  Informatica» si può verificare e correggere, «7 informazioni
                  su 8» no. Il conteggio resta, ma in coda, dov'è un dettaglio.
                */}
                <View style={styles.pillole}>
                  {(current.known || []).slice(0, 6).map((k) => (
                    <View key={k.ref} style={styles.pillola} testID={`guided-known-${k.ref}`}>
                      <Text style={[oraType.small, { color: ora.ink2 }]} numberOfLines={2}>
                        {k.label ? `${k.label}: ${k.value}` : k.value}
                      </Text>
                    </View>
                  ))}
                  <View style={styles.pillola}>
                    <Text style={[oraType.small, { color: ora.ink3 }]}>
                      {current.known_count} su {current.applicable_count} · {current.state_label}
                    </Text>
                  </View>
                </View>
              </View>
            ) : null}
            {current.open_objectives?.length ? (
              <View style={styles.sapereBlocco}>
                <View style={styles.sapereHead}>
                  <Ionicons name="time-outline" size={18} color={ora.attention} />
                  <Text style={[oraType.body, { color: ora.ink, fontWeight: '600' }]}>
                    Cosa manca per aiutarti meglio
                  </Text>
                </View>
                {/*
                  Queste non sono etichette: sono le cose che ORA non sa
                  ancora, e cliccarne una apre quella domanda lì. Prima erano
                  disegni, e chi le leggeva non aveva nessun modo di colmarle.
                */}
                <View style={styles.pillole}>
                  {current.open_objectives.slice(0, 3).map((o) => (
                    <Pressable
                      key={o.ref}
                      onPress={() => void goNextArea(current.area_id, o.ref)}
                      accessibilityRole="button"
                      accessibilityLabel={`Aggiungi: ${o.label}`}
                      style={({ pressed }: any) => [
                        styles.pillola,
                        { borderColor: ora.cta },
                        pressed && { opacity: 0.7 },
                      ]}
                      testID={`guided-gap-${o.ref}`}
                    >
                      <Text style={[oraType.small, { color: ora.cta, fontWeight: '600' }]}>
                        {o.label}
                      </Text>
                    </Pressable>
                  ))}
                </View>
              </View>
            ) : null}
          </View>
        ) : null}
        {/*
          Il prossimo passo dell'area selezionata, con le due CTA della
          reference. Compare quando la persona sta guardando un'area senza
          averci ancora messo mano: è il momento in cui decide se continuare
          adesso o più tardi — e «Continua con Casa» apre davvero la prima
          cosa che manca, invece di lasciarla dov'era.
        */}
        {/*
          Come sta quest'area, e cosa si può fare adesso.

              A UN'AREA COMPLETA NON SI CHIEDE DI CONTINUARE.

          Misurato in app (V3.21.3d): Lavoro al 100% mostrava «Continua con
          Lavoro» e «Lo faccio più tardi». Più tardi *che cosa*? Non c'era più
          niente da rimandare, e la CTA primaria portava a una domanda che non
          esisteva. Un'area finita si dichiara finita e tace.
        */}
        {current && !mostraDomanda ? (
          current.open_objectives?.length ? (
            <View style={styles.sapere} testID="guided-next-step">
              <View style={styles.sapereHead}>
                <Ionicons name="bulb-outline" size={18} color={ora.attention} />
                <Text style={[oraType.body, { color: ora.ink, fontWeight: '600' }]}>
                  Prossimo passo consigliato
                </Text>
              </View>
              {/*
                Le etichette del catalogo sono quasi tutte domande già scritte
                («Vuoi aggiungere il libretto?»), e infilarle in una frase
                faceva «Aggiungi vuoi aggiungere il libretto? per ricevere
                promemoria». Una domanda si legge com'è; il perché sta già nel
                riquadro qui sopra, che dice a cosa serve quest'area.
              */}
              <Text style={[oraType.small, { color: ora.ink2 }]}>
                {current.open_objectives[0].label.trim().endsWith('?')
                  ? current.open_objectives[0].label
                  : `Aggiungi ${current.open_objectives[0].label.toLowerCase()}.`}
              </Text>
              <View style={styles.ctaCoppia}>
                <Pressable
                  onPress={() => {
                    void goNextArea(current.area_id, undefined, true);
                  }}
                  accessibilityRole="button"
                  style={({ pressed }: any) => [
                    styles.primary,
                    { backgroundColor: ora.cta },
                    pressed && { opacity: 0.85 },
                  ]}
                  testID="guided-continue-area"
                >
                  <Text style={[styles.primaryText, { color: '#FFFFFF' }]}>
                    Continua con {current.title}
                  </Text>
                  <Ionicons name="arrow-forward" size={16} color="#FFFFFF" />
                </Pressable>
                <Pressable
                  onPress={() => void later()}
                  accessibilityRole="button"
                  style={({ pressed }: any) => [styles.secondary, pressed && { opacity: 0.7 }]}
                  testID="guided-later"
                >
                  <Ionicons name="time-outline" size={16} color={ora.ink2} />
                  <Text style={[styles.secondaryText, { color: ora.ink2 }]}>Lo faccio più tardi</Text>
                </Pressable>
              </View>
            </View>
          ) : current.percent >= 100 ? (
            <View style={styles.sapere} testID="guided-area-complete">
              <View style={styles.sapereHead}>
                <Ionicons name="checkmark-circle" size={18} color={ora.success} />
                <Text style={[oraType.body, { color: ora.ink, fontWeight: '600' }]}>
                  Di {current.title} so già tutto quello che mi serve.
                </Text>
              </View>
            </View>
          ) : (
            /*
              Non è piena, ma non c'è più niente che ORA possa chiedere: quello
              che manca è stato rifiutato, e un rifiuto è una risposta. Dire
              «so già tutto» qui sarebbe falso, e riproporre la domanda sarebbe
              non aver ascoltato.
            */
            <View style={styles.sapere} testID="guided-area-nothing-to-ask">
              <View style={styles.sapereHead}>
                <Ionicons name="checkmark-circle-outline" size={18} color={ora.ink3} />
                <Text style={[oraType.body, { color: ora.ink, fontWeight: '600' }]}>
                  Di {current.title} non ho altro da chiederti.
                </Text>
              </View>
              <Text style={[oraType.small, { color: ora.ink2 }]}>
                Quello che manca me l&apos;hai lasciato da parte, e va bene così.
              </Text>
            </View>
          )
        ) : null}
        {/*
          Dove andare dopo — staccata, perché parla di un'altra area.

          Compare solo quando qui non c'è più niente da chiedere: altrimenti
          sarebbe un invito ad andarsene a metà di un discorso. La frase è
          quella che manda il backend con il suo motivo, così quello che si
          legge («Casa è quasi completa: manca solo una cosa») è verificabile.
        */}
        {current && !mostraDomanda && !current.open_objectives?.length && consiglio ? (
          <View
            style={[styles.prossimaArea, { borderTopColor: ora.divider }]}
            testID="guided-next-area"
          >
            <Text style={[oraType.small, { color: ora.ink3, fontWeight: '600' }]}>
              Prossima area consigliata
            </Text>
            <Text style={[oraType.body, { color: ora.ink }]} testID="guided-next-area-reason">
              {consiglio.reason}
            </Text>
            <Pressable
              onPress={() => {
                void goNextArea(consiglio.area_id, undefined, true);
              }}
              accessibilityRole="button"
              style={({ pressed }: any) => [
                styles.primary,
                { backgroundColor: ora.cta, alignSelf: 'flex-start' },
                pressed && { opacity: 0.85 },
              ]}
              testID="guided-next-incomplete-area"
            >
              <Text style={[styles.primaryText, { color: '#FFFFFF' }]}>
                Completa {consiglio.title}
              </Text>
              <Ionicons name="arrow-forward" size={16} color="#FFFFFF" />
            </Pressable>
          </View>
        ) : null}
        {objective && mostraDomanda ? (
          <View style={styles.stepRow}>
            <Text style={[styles.stepText, { color: colors.textTertiary }]}>
              Passaggio {objective.step} di {objective.of}
            </Text>
            <View style={styles.stepBar}>
              <Bar
                percent={(objective.step / Math.max(objective.of, 1)) * 100}
                color={colors.accent}
                track={colors.divider}
              />
            </View>
          </View>
        ) : null}
        {transition}
        {mostraDomanda ? question : null}
      </View>
    </View>
  );

  const rail = (
    <View style={styles.rail} testID="guided-rail">
      <View style={[styles.railCard, { borderColor: colors.border, backgroundColor: colors.surface }]}>
        <Text style={[oraType.section, { color: ora.ink, marginBottom: 4 }]}>
          Le tue aree di vita
        </Text>
        {areas.map((a) => (
          // Stessa cosa qui: la colonna di destra è un indice, e un indice si
          // clicca. Porta allo stesso pannello centrale, non altrove.
          <Pressable
            key={a.area_id}
            onPress={() => void goNextArea(a.area_id)}
            accessibilityRole="button"
            accessibilityLabel={`Apri ${a.title}`}
            //     LA SELEZIONE È SOLO EVIDENZA VISIVA.
            // Bordo, sfondo e icona blu dicono dove sei. Non toccano né la
            // percentuale né l'etichetta di stato, che stanno a destra e
            // vengono da quello che ORA sa.
            accessibilityState={{ selected: !!a.selected }}
            style={({ pressed }: any) => [
              styles.railRow,
              { borderColor: a.selected ? colors.accent : colors.divider },
              a.selected && { backgroundColor: colors.accentMuted },
              pressed && { opacity: 0.7 },
            ]}
            testID={`guided-rail-${a.area_id}`}
          >
            <View style={[styles.railTile, { backgroundColor: a.selected ? colors.accent : colors.surfaceElevated }]}>
              <Ionicons
                name={areaIconName(a.icon_key)}
                size={15}
                color={a.selected ? colors.onAccent : colors.textTertiary}
              />
            </View>
            <Text style={[styles.railLabel, { color: colors.textPrimary }]} numberOfLines={1}>
              {a.title}
            </Text>
            <View style={styles.railRight}>
              <View style={[styles.railChip, { backgroundColor: colors.surfaceElevated }]}>
                <Text style={[styles.railState, { color: colors.textTertiary }]} numberOfLines={1}>
                  {stateLabel(a)}
                </Text>
              </View>
              <Text style={[styles.railPercent, { color: colors.textSecondary }]}>
                {a.percent}%
              </Text>
            </View>
          </Pressable>
        ))}
      </View>
      <View style={[styles.railNote, { backgroundColor: colors.surfaceElevated }]}>
        <Text style={[styles.railNoteText, { color: colors.textSecondary }]}>
          Puoi sospendere quando vuoi e riprendere da qui.
        </Text>
      </View>
      <Pressable onPress={() => void leave()} style={styles.linkRow} testID="guided-leave">
        <Text style={[styles.link, { color: colors.accent }]}>Salta per ora</Text>
      </Pressable>
    </View>
  );

  /*
    «In questo periodo».

        LE SITUAZIONI IN CORSO NON SPARISCONO, MA NON COMANDANO.

    La vecchia pagina Vita si apriva su queste — acquisto casa, mostra
    fotografica, piano di studio — ed era di fatto una seconda Home. Qui
    restano, in fondo, come quello che sono: le cose che stanno succedendo
    adesso, con il loro posto dove aprirle. Se non ce ne sono, la sezione non
    compare: una fascia vuota che dice «niente in corso» è una fascia che
    occupa spazio per non dire niente.
  */
  const periodo = situations.length ? (
    <View
      style={[styles.grow, { borderColor: colors.border, backgroundColor: colors.surface }]}
      testID="guided-periodo"
    >
      <View style={styles.growText}>
        <Text style={[styles.growTitle, { color: colors.textPrimary }]}>In questo periodo</Text>
        <Text style={[styles.growNote, { color: colors.textSecondary }]}>
          Le cose che stanno succedendo adesso nella tua vita.
        </Text>
        <View style={styles.periodoRighe}>
          {situations.slice(0, 4).map((sit) => (
            <Pressable
              key={sit.id}
              onPress={() => sit.href && router.push(sit.href as never)}
              accessibilityRole="button"
              accessibilityLabel={`Apri ${sit.title}`}
              style={({ pressed }: any) => [styles.periodoRiga, pressed && { opacity: 0.7 }]}
              testID={`guided-situazione-${sit.id}`}
            >
              <Ionicons name="ellipse" size={8} color={ora.cta} />
              <View style={{ flex: 1 }}>
                <Text style={[oraType.body, { color: ora.ink }]} numberOfLines={1}>
                  {sit.title}
                </Text>
                {sit.temporal || sit.summary ? (
                  <Text style={[oraType.small, { color: ora.ink3 }]} numberOfLines={1}>
                    {sit.temporal || sit.summary}
                  </Text>
                ) : null}
              </View>
              <Ionicons name="chevron-forward" size={15} color={ora.ink3} />
            </Pressable>
          ))}
        </View>
      </View>
    </View>
  ) : null;

  return (
    <DesktopShell active="contesti">
    <SafeAreaView
      style={[styles.root, { backgroundColor: ora.canvas }]}
      testID="guided-setup"
    >
      <View style={styles.shell}>
        {/*
          V3.21.3: la navigazione qui era una lista di parole tutta sua. Adesso
          è la barra laterale del prodotto, la stessa della Home — e questa
          schermata smette di sembrare un'altra applicazione.
        */}
      <ScrollView style={{ flex: 1 }} contentContainerStyle={styles.scroll}>
        <View style={[styles.page, twoColumn && styles.pageWide]}>
          <View style={styles.main}>
            {header}
            {perche}
            {intro}
            {profileCard}
            <View style={{ backgroundColor: ora.surface, borderRadius: tokens.radius.xl, borderWidth: 1, borderColor: colors.border, padding: 20, gap: 10 }} testID="vita-bank-space">
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                <Ionicons name="wallet-outline" size={24} color={ora.cta} />
                <Text style={[styles.cardTitle, { color: ora.ink }]}>La tua banca</Text>
              </View>
              <Text style={[oraType.body, { color: ora.ink2 }]}>Uno spazio per conti, saldi e movimenti.</Text>
              <Text style={[oraType.small, { color: ora.ink2 }]}>Ambiente di prova · ORA LOCAL. Il collegamento usa conti simulati, non il tuo conto reale.</Text>
              <Pressable accessibilityRole="button" accessibilityLabel="Prova il collegamento bancario" onPress={() => router.push('/collega-conto')} style={{ backgroundColor: ora.cta, borderRadius: 12, padding: 14, alignSelf: 'flex-start' }}>
                <Text style={{ color: '#fff', fontWeight: '600' }}>Prova il collegamento</Text>
              </Pressable>
              <Pressable accessibilityRole="link" onPress={() => router.push('/conti-e-denaro')}>
                <Text style={{ color: ora.cta }}>Vedi conti e movimenti →</Text>
              </Pressable>
            </View>
            {error ? (
              <Text style={[styles.error, { color: colors.error }]} testID="guided-error">
                {error}
              </Text>
            ) : null}
            {areaCard}
            {!twoColumn ? path : null}
          </View>
          {twoColumn ? <View style={{ width: RAIL }}>{rail}</View> : rail}
        </View>
        <View style={[styles.page, { maxWidth: 1240 }]}>{periodo}</View>
      </ScrollView>
      </View>
    </SafeAreaView>
    </DesktopShell>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  scroll: { padding: tokens.spacing.lg, paddingBottom: 48 },
  page: { gap: tokens.spacing.lg, alignSelf: 'center', width: '100%', maxWidth: 1240 },
  pageWide: { flexDirection: 'row', alignItems: 'flex-start' },
  main: { flex: 1, gap: tokens.spacing.lg },

  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  sapere: { gap: 16, marginTop: 8 },
  sapereBlocco: { gap: 8 },
  sapereHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  pillole: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  pillola: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: ora.hairline,
    backgroundColor: ora.surface,
    borderRadius: 999,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  back: { minHeight: 44, justifyContent: 'center' },
  backText: { fontSize: 14 },
  why: {
    minHeight: 44,
    justifyContent: 'center',
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.pill,
    paddingHorizontal: 16,
  },
  whyText: { fontSize: 13 },

  intro: { gap: 8, maxWidth: 470, flexShrink: 1 },
  perche: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    padding: 14,
    borderRadius: 14,
  },
  introRiga: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 28,
  },
  //     UNA FASCIA SOLA, ALTA QUANTO LA TESTATA.
  // La reference non mette un riquadro accanto al titolo: mette una fascia
  // calda che prende tutta l'altezza dell'intestazione, con la frase scritta
  // sopra la parete vuota e gli oggetti a destra. Il fondo della fascia è il
  // bianco caldo della fotografia, così il passaggio fra interfaccia e
  // scatto non si vede. E la frase tiene la sua misura: con tutto flessibile
  // andava a capo a ogni parola.
  testata: {
    flex: 1,
    minWidth: 560,
    height: 156,
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: 18,
    overflow: 'hidden',
    // Il tono è la media del bordo sinistro della fotografia: se il fondo
    // della fascia è di un beige suo, fra interfaccia e scatto si vede la
    // giunta.
    backgroundColor: '#F6ECE3',
  },
  testataFoto: { flex: 1, height: '100%' },
  nota: {
    fontSize: 16,
    lineHeight: 24,
    fontStyle: 'italic',
    textAlign: 'center',
    width: 186,
    paddingHorizontal: 10,
    flexShrink: 0,
  },
  title: { fontSize: 34, fontWeight: '700', letterSpacing: -0.6 },
  introText: { fontSize: 15, lineHeight: 22 },

  profile: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.lg,
    padding: tokens.spacing.md,
    gap: 8,
  },
  profileHead: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between' },
  profileTitle: { fontSize: 12, letterSpacing: 0.6 },
  profilePercent: { fontSize: 22, fontWeight: '700' },
  profileNote: { fontSize: 12 },

  track: { height: 5, borderRadius: 3, overflow: 'hidden' },
  fill: { height: '100%', borderRadius: 3 },

  card: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.xl,
    flexDirection: 'row',
    overflow: 'hidden',
  },
  cardPath: {
    width: 244,
    padding: tokens.spacing.md,
    borderRightWidth: StyleSheet.hairlineWidth,
    borderRightColor: 'rgba(0,0,0,0.06)',
  },
  cardBody: { flex: 1, padding: tokens.spacing.lg, gap: tokens.spacing.sm },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  cardTitle: { fontSize: 20, fontWeight: '700' },
  cardSub: { fontSize: 14 },
  chip: { borderRadius: tokens.radius.pill, paddingHorizontal: 10, paddingVertical: 4 },
  chipText: { fontSize: 12, fontWeight: '600' },

  stepRow: { gap: 6, marginTop: 4 },
  stepText: { fontSize: 12 },
  stepBar: { maxWidth: 320 },

  path: { gap: 4 },
  pathTitle: { fontSize: 11, letterSpacing: 0.6, marginBottom: 6 },
  pathRow: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderRadius: tokens.radius.md,
    paddingHorizontal: 8,
  },
  pathTile: {
    width: 28,
    height: 28,
    borderRadius: tokens.radius.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pathNum: { fontSize: 11, width: 14, textAlign: 'right' },
  headTile: {
    width: 34,
    height: 34,
    borderRadius: tokens.radius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  railTile: {
    width: 26,
    height: 26,
    borderRadius: tokens.radius.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pathLabel: { fontSize: 14, flex: 1 },

  question: { gap: tokens.spacing.sm, marginTop: 8 },
  questionText: { fontSize: 17, fontWeight: '600' },
  questionHint: { fontSize: 13 },
  options: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 4 },
  option: {
    minHeight: 84,
    minWidth: 104,
    flexGrow: 1,
    // Wide enough for a whole sentence. “Sono incluse nel canone o nel
    // condominio” has to be readable without a tooltip and without an
    // ellipsis, so the basis follows the longest label rather than the
    // shortest.
    flexBasis: 168,
    maxWidth: 260,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.lg,
    padding: tokens.spacing.md,
    justifyContent: 'center',
    gap: 4,
  },
  optionLabel: { fontSize: 14, fontWeight: '500' },
  optionDesc: { fontSize: 12 },

  otherBox: { gap: 8, marginTop: 4 },
  docBox: { gap: 8, marginTop: 4, alignItems: 'flex-start' },
  uploadBtn: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.md,
    paddingHorizontal: 16,
  },
  uploadText: { fontSize: 14, fontWeight: '500' },
  input: {
    minHeight: 48,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.md,
    paddingHorizontal: 14,
    fontSize: 15,
  },

  privacy: { borderRadius: tokens.radius.md, padding: tokens.spacing.md, marginTop: 8 },
  privacyText: { fontSize: 12, lineHeight: 18 },

  actions: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: tokens.spacing.sm,
    marginTop: tokens.spacing.sm,
    flexWrap: 'wrap',
  },
  actionsRight: { flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.md },
  primary: {
    minHeight: 44,
    borderRadius: tokens.radius.md,
    paddingHorizontal: 22,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryText: { fontSize: 15, fontWeight: '600' },
  secondary: {
    minHeight: 44,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.md,
    paddingHorizontal: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  secondaryText: { fontSize: 14 },
  //     «DOPO» È UN'ALTRA COSA: SI VEDE CHE È UN'ALTRA COSA.
  // Una riga sopra e un po' d'aria bastano perché il consiglio non si
  // legga come la continuazione dell'area che si sta guardando.
  prossimaArea: {
    gap: 10,
    marginTop: 24,
    paddingTop: 20,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  ctaCoppia: { flexDirection: 'row', alignItems: 'center', gap: 14, flexWrap: 'wrap', marginTop: 4 },
  periodoRighe: { marginTop: 12, gap: 2 },
  periodoRiga: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingVertical: 10,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: ora.divider,
  },
  linkRow: { minHeight: 44, justifyContent: 'center' },
  link: { fontSize: 13, fontWeight: '500' },

  transition: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.lg,
    padding: tokens.spacing.md,
    gap: 8,
    alignItems: 'flex-start',
  },
  transitionTitle: { fontSize: 16, fontWeight: '600' },
  transitionNote: { fontSize: 13, lineHeight: 19 },

  rail: { gap: tokens.spacing.md },
  railCard: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.lg,
    padding: tokens.spacing.md,
    gap: 6,
  },
  railTitle: { fontSize: 11, letterSpacing: 0.6, marginBottom: 4 },
  railRow: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.md,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  railLabel: { fontSize: 14, flex: 1 },
  railRight: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  railState: { fontSize: 11 },
  railPercent: { fontSize: 12, fontVariant: ['tabular-nums'] },
  railNote: { borderRadius: tokens.radius.md, padding: tokens.spacing.md },
  railNoteText: { fontSize: 12, lineHeight: 18 },

  error: { fontSize: 13 },

  shell: { flex: 1, flexDirection: 'row' },
  nav: {
    width: 200,
    paddingVertical: tokens.spacing.lg,
    paddingHorizontal: tokens.spacing.md,
    borderRightWidth: StyleSheet.hairlineWidth,
    gap: 4,
  },
  navBrand: { fontSize: 20, fontWeight: '700', marginBottom: tokens.spacing.md },
  navRow: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 10 },
  navLabel: { fontSize: 15 },
  navSpacer: { flex: 1, minHeight: 24 },

  grow: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.lg,
    padding: tokens.spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: tokens.spacing.md,
    flexWrap: 'wrap',
  },
  growText: { flex: 1, minWidth: 220, gap: 2 },
  growTitle: { fontSize: 15, fontWeight: '600' },
  growNote: { fontSize: 13 },

  railChip: { borderRadius: tokens.radius.pill, paddingHorizontal: 8, paddingVertical: 3 },
});
