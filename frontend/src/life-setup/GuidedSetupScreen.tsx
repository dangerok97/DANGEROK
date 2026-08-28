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
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

import { api, GuidedObjective, GuidedSetupState } from '@/src/api/client';
import { areaIconName } from '@/src/components/life-profile/areaIcon';
import { requestDevicePosition } from '@/src/life-setup/devicePosition';
import * as DocumentPicker from 'expo-document-picker';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { humanizeError } from '@/src/utils/errors';

const TWO_COLUMN_AT = 1000;
const RAIL = 360;

/** Every state an area can be in, said the way a person would say it. */
function stateLabel(area: { state: string; state_label: string; current?: boolean; skipped?: boolean }) {
  if (area.current) return 'In corso';
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

  const objective = state?.objective ?? null;
  const areas = state?.areas ?? [];
  const current = areas.find((a) => a.area_id === state?.current_area_id) || null;

  const load = useCallback(async () => {
    try {
      const res = await api.guidedSetupState();
      setState(res);
      setError(null);
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

  const goNextArea = useCallback(
    async (areaId: string) => {
      setBusy(true);
      try {
        setState(await api.guidedSetupGoToArea(areaId));
        reset();
      } catch (e) {
        setError(humanizeError(e, 'default'));
      } finally {
        setBusy(false);
      }
    },
    [reset],
  );

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
      <View
        style={[styles.why, { borderColor: colors.border, backgroundColor: colors.surface }]}
        testID="guided-why"
      >
        <Text style={[styles.whyText, { color: colors.textSecondary }]}>
          Perché queste domande?
        </Text>
      </View>
    </View>
  );

  const intro = (
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
  );

  const profileCard = (
    <View
      style={[styles.profile, { borderColor: colors.border, backgroundColor: colors.surface }]}
      testID="guided-profile"
    >
      <View style={styles.profileHead}>
        <Text style={[styles.profileTitle, { color: colors.textSecondary }]}>PROFILO VITA</Text>
        <Text style={[styles.profilePercent, { color: colors.textPrimary }]} testID="guided-percent">
          {percent}%
        </Text>
      </View>
      <Bar percent={percent} color={colors.accent} track={colors.divider} />
      <Text style={[styles.profileNote, { color: colors.textTertiary }]}>
        Quello che ORA sa di te. Puoi completarlo nel tempo.
      </Text>
    </View>
  );

  const path = (
    <View style={styles.path} testID="guided-path">
      <Text style={[styles.pathTitle, { color: colors.textTertiary }]}>PERCORSO</Text>
      {areas.map((a, i) => {
        const isCurrent = a.area_id === state?.current_area_id;
        return (
          <View
            key={a.area_id}
            style={[
              styles.pathRow,
              isCurrent && { backgroundColor: colors.accentMuted },
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
          </View>
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

  const done = !objective && !state?.transition ? (
    <View style={styles.question} testID="guided-done">
      <Text style={[styles.questionText, { color: colors.textPrimary }]}>
        ORA ha un buon punto di partenza.
      </Text>
      <Text style={[styles.questionHint, { color: colors.textSecondary }]}>
        Conosce il {percent}% di ciò che può aiutarti. Puoi aggiungere il resto quando vuoi, da
        Vita.
      </Text>
      <Pressable
        onPress={() => void leave()}
        accessibilityRole="button"
        style={[styles.primary, { backgroundColor: colors.accent, alignSelf: 'flex-start' }]}
        testID="guided-enter"
      >
        <Text style={[styles.primaryText, { color: colors.onAccent }]}>Entra in ORA</Text>
      </Pressable>
    </View>
  ) : null;

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
            <View style={[styles.chip, { backgroundColor: colors.accentMuted }]}>
              <Text style={[styles.chipText, { color: colors.accent }]}>In corso</Text>
            </View>
          </View>
        ) : null}
        {current ? (
          <Text style={[styles.cardSub, { color: colors.textSecondary }]}>
            {current.description}
          </Text>
        ) : null}
        {objective ? (
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
        {question}
        {done}
      </View>
    </View>
  );

  const rail = (
    <View style={styles.rail} testID="guided-rail">
      <View style={[styles.railCard, { borderColor: colors.border, backgroundColor: colors.surface }]}>
        <Text style={[styles.railTitle, { color: colors.textTertiary }]}>LE TUE AREE</Text>
        {areas.map((a) => (
          <View
            key={a.area_id}
            style={[
              styles.railRow,
              { borderColor: a.current ? colors.accent : colors.divider },
              a.current && { backgroundColor: colors.accentMuted },
            ]}
            testID={`guided-rail-${a.area_id}`}
          >
            <View style={[styles.railTile, { backgroundColor: a.current ? colors.accent : colors.surfaceElevated }]}>
              <Ionicons
                name={areaIconName(a.icon_key)}
                size={15}
                color={a.current ? colors.onAccent : colors.textTertiary}
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
          </View>
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

  const nav = (
    <View style={[styles.nav, { borderRightColor: colors.divider }]} testID="guided-nav">
      <Text style={[styles.navBrand, { color: colors.accent }]}>ORA</Text>
      {[
        { label: 'Home', href: '/' },
        { label: 'Vita', href: '/contesti' },
        { label: 'ORA', href: '/ora' },
        { label: 'Attività', href: '/attivita' },
        { label: 'Documenti', href: '/documenti' },
      ].map((item) => (
        <Pressable
          key={item.href}
          onPress={() => router.push(item.href as never)}
          accessibilityRole="link"
          accessibilityLabel={item.label}
          style={styles.navRow}
          testID={`guided-nav-${item.label.toLowerCase()}`}
        >
          <Text style={[styles.navLabel, { color: colors.textSecondary }]}>{item.label}</Text>
        </Pressable>
      ))}
      <View style={styles.navSpacer} />
      <Pressable
        onPress={() => router.push('/settings' as never)}
        accessibilityRole="link"
        accessibilityLabel="Impostazioni"
        style={styles.navRow}
        testID="guided-nav-impostazioni"
      >
        <Text style={[styles.navLabel, { color: colors.textTertiary }]}>Impostazioni</Text>
      </Pressable>
    </View>
  );

  const growBanner = (
    <View
      style={[styles.grow, { borderColor: colors.border, backgroundColor: colors.surfaceElevated }]}
      testID="guided-grow"
    >
      <View style={styles.growText}>
        <Text style={[styles.growTitle, { color: colors.textPrimary }]}>ORA cresce con te</Text>
        <Text style={[styles.growNote, { color: colors.textSecondary }]}>
          Più condividi, più consigli e promemoria saranno utili e personalizzati.
        </Text>
      </View>
      <Pressable
        onPress={() => router.push('/contesti')}
        accessibilityRole="button"
        style={[styles.primary, { backgroundColor: colors.accent }]}
        testID="guided-see-known"
      >
        <Text style={[styles.primaryText, { color: colors.onAccent }]}>
          Vedi cosa ho già capito di te
        </Text>
      </Pressable>
    </View>
  );

  return (
    <SafeAreaView
      style={[styles.root, { backgroundColor: colors.backgroundPrimary }]}
      testID="guided-setup"
    >
      <View style={styles.shell}>
        {twoColumn ? nav : null}
      <ScrollView style={{ flex: 1 }} contentContainerStyle={styles.scroll}>
        <View style={[styles.page, twoColumn && styles.pageWide]}>
          <View style={styles.main}>
            {header}
            {intro}
            {profileCard}
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
        <View style={[styles.page, { maxWidth: 1240 }]}>{growBanner}</View>
      </ScrollView>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  scroll: { padding: tokens.spacing.lg, paddingBottom: 48 },
  page: { gap: tokens.spacing.lg, alignSelf: 'center', width: '100%', maxWidth: 1240 },
  pageWide: { flexDirection: 'row', alignItems: 'flex-start' },
  main: { flex: 1, gap: tokens.spacing.lg },

  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
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

  intro: { gap: 8, maxWidth: 620 },
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
