/**
 * Canonical production ORA composer — Quiet Premium.
 * Real file attachments via Documents V2 + AI Core ContextFile bind.
 */
import React from 'react';
import {
  ActivityIndicator,
  Image,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { OraAttachMenu, type AttachKind } from './OraAttachMenu';

export type { AttachKind };

export type PendingAttachment = {
  localId: string;
  fileId?: string;
  documentId?: string;
  name: string;
  mimeType: string;
  status: 'uploading' | 'ready' | 'failed';
  error?: string;
  textAvailable?: boolean;
  /**
   * Dove sta l'immagine sul dispositivo, per mostrarla mentre parte.
   *
   * Di una fotografia si mostra la fotografia: «IMG_20260911_204413.png» non
   * dice a nessuno quale delle quattro schermate ha appena mandato, e chi
   * l'ha scattata la riconosce a colpo d'occhio.
   */
  previewUri?: string;
};

type Props = {
  value: string;
  onChangeText: (t: string) => void;
  onSend: () => void;
  busy?: boolean;
  disabled?: boolean;
  placeholder?: string;
  testID?: string;
  showAttach?: boolean;
  attachments?: PendingAttachment[];
  /**
   * Cosa si è scelto di aggiungere, non «ha toccato il piu'».
   *
   * Il composer non sa aprire niente: sa solo chiedere. Quale selettore
   * si apra è una decisione di chi possiede la conversazione, ed è lì che
   * vive anche il caricamento.
   */
  onAttachPress?: (kind: AttachKind) => void;
  onRemoveAttachment?: (localId: string) => void;
  showMicStub?: boolean;
  onMicPress?: () => void;
  /** Sta ascoltando adesso. */
  listening?: boolean;
  /** Sta parlando adesso: toccare il microfono la interrompe e riapre l'ascolto. */
  speaking?: boolean;
  /** Quello che si sta sentendo, mentre lo si sente. */
  interim?: string;
  /** «Ti ascolto», o cosa non ha funzionato. */
  voiceHint?: string | null;
  /** Entra nella conversazione a voce. Assente dove non ha senso. */
  onVoiceModePress?: () => void;
  /**
   * The rule above the composer separates it from content scrolling under it.
   * In the opening state nothing scrolls, and the line reads as a stray divider
   * cutting the invitation in half.
   */
  divider?: boolean;
};

export function OraComposer({
  value,
  onChangeText,
  onSend,
  busy,
  disabled,
  placeholder = 'Messaggio…',
  testID = 'ora-composer',
  showAttach = true,
  attachments = [],
  onAttachPress,
  onRemoveAttachment,
  showMicStub = true,
  onMicPress,
  listening = false,
  speaking = false,
  interim = '',
  voiceHint = null,
  onVoiceModePress,
  divider = true,
}: Props) {
  const { colors, isDark } = useTheme();
  /*
    Il campo cresce con quello che ci si scrive, entro un limite. Senza
    questo, su web un campo multilinea resta alto una riga e il testo scorre
    dentro una fessura; con un'altezza fissa generosa, invece, occupa mezzo
    schermo anche quando è vuoto.
  */
  const [grown, setGrown] = React.useState(24);
  const [focused, setFocused] = React.useState(false);
  /*
    Il menu del «+» sta aperto qui e non nella schermata: è ancorato al
    pulsante, e chi lo apre deve poter sapere che è aperto per disegnarlo
    premuto. Chiudendolo prima di eseguire la scelta, il selettore di
    sistema non si apre sopra un menu rimasto acceso.
  */
  const [menuOpen, setMenuOpen] = React.useState(false);
  /*
    Dove torna il focus quando il menu si chiude.

    Chiudendo con Esc da una voce del menu, quella voce sparisce e il focus
    finisce sul corpo della pagina: chi stava navigando con la tastiera
    ricomincia da capo. Torna dove era prima di aprire, cioè sul «+».
  */
  const plusRef = React.useRef<any>(null);
  const closeMenu = React.useCallback(() => {
    setMenuOpen(false);
    try {
      plusRef.current?.focus?.();
    } catch {
      // Su nativo non c'è un focus da restituire, e non è un errore.
    }
  }, []);
  /*
    Mentre ascolta, il campo mostra quello che sta sentendo invece di quello
    che era stato scritto. Non è una modalità diversa: è la stessa riga, che
    per qualche secondo la riempie la voce. Quando ha finito, le parole
    partono da sole e la riga torna vuota.
  */
  const shown = listening && interim ? interim : value;
  const hasReadyFile = attachments.some((a) => a.status === 'ready');
  const uploading = attachments.some((a) => a.status === 'uploading');
  const canSend =
    (Boolean(value.trim()) || hasReadyFile) && !busy && !disabled && !uploading;

  return (
    <View testID={testID}>
      {attachments.length ? (
        <View style={styles.chips} testID={`${testID}-attachments`}>
          {attachments.map((a) => (
            <View
              key={a.localId}
              style={[
                styles.chip,
                {
                  backgroundColor: colors.surface || colors.backgroundSecondary,
                  borderColor: colors.border,
                },
              ]}
            >
              <Ionicons
                name={a.status === 'failed' ? 'alert-circle-outline' : 'document-outline'}
                size={16}
                color={a.status === 'failed' ? colors.error : colors.textSecondary}
              />
              {a.previewUri && a.mimeType?.startsWith('image/') ? (
                <Image
                  source={{ uri: a.previewUri }}
                  style={styles.thumb}
                  accessibilityIgnoresInvertColors
                  testID={`${testID}-thumb-${a.localId}`}
                />
              ) : null}
              <Text
                style={[
                  styles.chipText,
                  {
                    color:
                      a.status === 'failed' ? colors.error : colors.textPrimary,
                  },
                ]}
                numberOfLines={1}
              >
                {a.status === 'uploading'
                  ? `Caricamento… ${a.name}`
                  : a.status === 'failed'
                    ? a.error || `Errore: ${a.name}`
                    : a.name}
              </Text>
              {a.status === 'uploading' ? (
                <ActivityIndicator size="small" color={colors.textSecondary} />
              ) : (
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={`Rimuovi allegato ${a.name}`}
                  onPress={() => onRemoveAttachment?.(a.localId)}
                  style={styles.chipRemove}
                  testID={`${testID}-remove-${a.localId}`}
                >
                  <Ionicons name="close" size={16} color={colors.textTertiary} />
                </Pressable>
              )}
            </View>
          ))}
        </View>
      ) : null}

      {voiceHint ? (
        <Text
          style={[styles.voiceHint, { color: colors.textTertiary }]}
          testID={`${testID}-voice-hint`}
        >
          {voiceHint}
        </Text>
      ) : null}

      {/*
        Un contenitore solo, e i comandi sotto invece che addosso.

            IL POSTO DOVE SI SCRIVE DEVE ESSERE PIÙ GRANDE DI QUELLO CHE LO
            CIRCONDA.

        Prima allegato, microfono, onda e invio stavano in fila accanto al
        campo: su un telefono da 390 punti restavano centoquaranta punti per
        scrivere, e «Scrivi a ORA…» andava a capo dentro il suo stesso
        segnaposto. Adesso il campo prende tutta la larghezza e i comandi
        vivono sulla riga sotto — allegare a sinistra, parlare e mandare a
        destra — che è anche l'ordine in cui una persona li cerca.
      */}
      <View
        style={[
          styles.shellWrap,
          { borderTopColor: divider ? colors.border : 'transparent' },
        ]}
      >
        <View
          style={[
            styles.shell,
            {
              backgroundColor: colors.surface || colors.backgroundSecondary,
              borderColor: focused ? colors.textTertiary : colors.border,
            },
          ]}
          testID={`${testID}-shell`}
        >
          <TextInput
            testID={`${testID}-input`}
            value={shown}
            onChangeText={onChangeText}
            placeholder={listening ? 'Ti ascolto…' : placeholder}
            placeholderTextColor={colors.placeholder || colors.textSecondary}
            style={[
              styles.input,
              { color: colors.textPrimary, height: Math.min(Math.max(grown, 24), 132) },
            ]}
            editable={!busy && !disabled && !listening}
            multiline
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            onContentSizeChange={(e) => setGrown(e.nativeEvent.contentSize.height)}
            onSubmitEditing={() => {
              if (canSend) onSend();
            }}
            returnKeyType="send"
            keyboardAppearance={isDark ? 'dark' : 'light'}
          />

          <View style={styles.controls}>
            {showAttach ? (
              <View style={styles.anchor}>
                <Pressable
                  ref={plusRef}
                  accessibilityRole="button"
                  accessibilityLabel="Aggiungi foto, file o documenti"
                  accessibilityState={{
                    disabled: busy || disabled || uploading,
                    expanded: menuOpen,
                  }}
                  onPress={() => setMenuOpen((was) => !was)}
                  disabled={busy || disabled || uploading}
                  style={[
                    styles.iconBtn,
                    menuOpen && {
                      backgroundColor: colors.backgroundSecondary,
                      borderRadius: tokens.touch.min / 2,
                    },
                  ]}
                  testID={`${testID}-attach`}
                >
                  <Ionicons
                    name="add"
                    size={22}
                    color={menuOpen ? colors.textPrimary : colors.textTertiary}
                  />
                </Pressable>
                <OraAttachMenu
                  open={menuOpen}
                  onClose={closeMenu}
                  onChoose={(kind) => onAttachPress?.(kind)}
                  testID={`${testID}-attach-menu`}
                  /*
                    Sopra tutto il contenitore, non solo sopra il pulsante:
                    44 del pulsante + 4 della riga + il campo + 16 di margine,
                    e otto punti d'aria. Il campo cresce, e il menu con lui.
                  */
                  lift={72 + Math.min(Math.max(grown, 24), 132)}
                />
              </View>
            ) : null}

            <View style={styles.gap} />

            {showMicStub ? (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={
                  listening ? 'Ho finito di dettare' : 'Detta un messaggio'
                }
                accessibilityState={{ disabled: (busy && !listening) || disabled }}
                onPress={onMicPress}
                disabled={(busy && !listening) || disabled}
                style={styles.iconBtn}
                testID={`${testID}-mic`}
              >
                <Ionicons
                  name={listening ? 'mic' : 'mic-outline'}
                  size={20}
                  color={listening ? colors.accent : colors.textTertiary}
                />
              </Pressable>
            ) : null}

            {onVoiceModePress ? (
              /*
                Il secondo controllo, e la distinzione è tutta qui: il
                microfono serve a dire una cosa invece di scriverla, questo a
                parlarsi. Barre d'audio, non una linea da elettrocardiogramma:
                le barre dicono «voce», il tracciato dice «monitor».
              */
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Parla con ORA a voce"
                accessibilityState={{ disabled: disabled }}
                onPress={onVoiceModePress}
                disabled={disabled}
                style={styles.iconBtn}
                testID={`${testID}-voice-mode`}
              >
                <VoiceWave tint={speaking ? colors.accent : colors.textTertiary} />
              </Pressable>
            ) : null}

            <Pressable
              testID={`${testID}-send`}
              accessibilityRole="button"
              accessibilityLabel="Invia messaggio"
              accessibilityState={{ disabled: !canSend, busy }}
              onPress={onSend}
              disabled={!canSend}
              style={({ pressed }) => [
                styles.send,
                {
                  backgroundColor: canSend ? colors.textPrimary : 'transparent',
                  opacity: !canSend ? 0.35 : pressed ? 0.85 : 1,
                },
              ]}
            >
              {busy ? (
                <ActivityIndicator color={colors.backgroundPrimary} size="small" />
              ) : (
                <Ionicons
                  name="arrow-up"
                  size={18}
                  color={canSend ? colors.backgroundPrimary : colors.textTertiary}
                />
              )}
            </Pressable>
          </View>
        </View>
      </View>
    </View>
  );
}

/**
 * Quattro barre di altezza diversa: una voce, non un equalizzatore.
 *
 *     UN'ICONA SI CAPISCE PRIMA DI LEGGERLA, O NON SI CAPISCE.
 *
 * Prima qui c'erano i tre cursori di `options-outline`, e tre cursori sono le
 * impostazioni: chi li vede accanto a un microfono pensa «preferenze audio»,
 * non «parliamo». Ionicons non ha una forma d'onda, e infilarci dentro un
 * tracciato da elettrocardiogramma dice «monitor» invece di «voce». Quattro
 * barrette disuguali invece si leggono come suono e basta, e sono venti righe.
 */
function VoiceWave({ tint }: { tint: string }) {
  return (
    <View style={styles.wave} accessible={false}>
      {[9, 17, 13, 7].map((height, i) => (
        <View
          key={i}
          style={[styles.waveBar, { height, backgroundColor: tint }]}
        />
      ))}
    </View>
  );
}

const DOCUMENT_KINDS = [
  'application/pdf',
  'text/plain',
  'text/markdown',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/msword',
];
const IMAGE_KINDS = ['image/*'];

/**
 * Quello che si apre, per ognuna delle voci del menu.
 *
 * «Foto» e «Fotocamera» chiedono la stessa cosa — un'immagine — ma non nello
 * stesso posto: la prima nella libreria, la seconda dall'obiettivo. Su web la
 * differenza è una parola, `capture`, e il browser di un telefono ci apre
 * sopra la fotocamera.
 */
function whatToAsk(kind: AttachKind) {
  if (kind === 'photo' || kind === 'camera') {
    return { accept: IMAGE_KINDS, capture: kind === 'camera' };
  }
  if (kind === 'document') return { accept: DOCUMENT_KINDS, capture: false };
  return { accept: [...DOCUMENT_KINDS, ...IMAGE_KINDS], capture: false };
}

/**
 * Un file dal dispositivo, del tipo che è stato chiesto.
 *
 * Su web si costruisce l'input a mano invece di passare per il selettore di
 * Expo: quello non sa dire `capture`, e senza `capture` «Fotocamera» sarebbe
 * la stessa identica finestra di «Foto» con un nome diverso — cioè una bugia
 * piccola, ripetuta ogni volta.
 */
export async function pickOraAttachment(
  kind: AttachKind = 'any',
): Promise<{ uri: string; name: string; type: string } | null> {
  const asked = whatToAsk(kind);

  if (Platform.OS === 'web' && typeof document !== 'undefined') {
    return await new Promise((resolve) => {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = asked.accept.join(',');
      if (asked.capture) input.setAttribute('capture', 'environment');
      input.style.display = 'none';
      let settled = false;
      const done = (value: { uri: string; name: string; type: string } | null) => {
        if (settled) return;
        settled = true;
        input.remove();
        resolve(value);
      };
      input.onchange = () => {
        const file = input.files?.[0];
        if (!file) return done(null);
        done({
          uri: URL.createObjectURL(file),
          name: file.name || 'file.bin',
          type: file.type || 'application/octet-stream',
        });
      };
      // Chiudere la finestra del sistema senza scegliere niente non produce
      // nessun evento in alcuni browser: senza questo, la promessa resterebbe
      // appesa e il «+» non si riaprirebbe più.
      input.oncancel = () => done(null);
      document.body.appendChild(input);
      input.click();
    });
  }

  // Dynamic import keeps web bundle resilient if native module missing
  const DocumentPicker = await import('expo-document-picker');
  const res = await DocumentPicker.getDocumentAsync({
    type: asked.accept,
    multiple: false,
    copyToCacheDirectory: true,
  });
  if (res.canceled || !res.assets?.length) return null;
  const a = res.assets[0];
  return {
    uri: a.uri,
    name: a.name || 'file.bin',
    type: a.mimeType || 'application/octet-stream',
  };
}


const styles = StyleSheet.create({
  chips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    paddingHorizontal: tokens.spacing.md,
    paddingTop: 8,
  },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    maxWidth: '100%',
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: 10,
    borderWidth: StyleSheet.hairlineWidth,
  },
  chipText: { fontSize: 13, flexShrink: 1, maxWidth: 220 },
  thumb: { width: 28, height: 28, borderRadius: 6, marginLeft: -2 },
  voiceHint: {
    fontSize: 13,
    lineHeight: 18,
    paddingHorizontal: tokens.spacing.lg,
    paddingBottom: 6,
  },
  shellWrap: {
    paddingHorizontal: tokens.spacing.md,
    paddingTop: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  shell: {
    borderRadius: tokens.radius.xl,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: tokens.spacing.md,
    paddingTop: tokens.spacing.md,
    paddingBottom: 6,
  },
  controls: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 4,
  },
  /*
    Il pulsante e il suo menu stanno nella stessa scatola, così il menu si
    posiziona rispetto al «+» invece che rispetto al composer: se un giorno
    i comandi cambiano ordine, il menu si sposta con il suo pulsante.
  */
  anchor: { position: 'relative' },
  gap: { flex: 1 },
  wave: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    height: 20,
  },
  waveBar: { width: 2.5, borderRadius: 1.5 },
  /*
    The composer's two icon controls were 40px and, lacking a button role,
    reached neither the keyboard nor a screen reader as controls at all — they
    were labelled text. The glyph is unchanged; the box around it is now the
    44px floor, and the role travels with it.
  */
  iconBtn: {
    width: tokens.touch.min,
    height: tokens.touch.min,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 2,
  },
  input: {
    width: '100%',
    minHeight: 24,
    maxHeight: 132,
    paddingHorizontal: 0,
    paddingVertical: 0,
    fontSize: 16,
    lineHeight: 22,
    textAlignVertical: 'top',
    // Il campo non ha più un bordo suo: il bordo è quello del contenitore, e
    // due bordi concentrici a due punti di distanza sono una cornice.
    outlineStyle: 'none' as any,
  },
  /*
    The send button only exists once there is something to send, which is how
    it slipped past the tap-target pass that fixed attach and voice. It is now
    the same 44px box as its two neighbours — the row reads as three equal
    controls rather than two and a slightly smaller one.
  */
  /*
    `hitSlop` is honoured on device and ignored by the web renderer, so the
    cross that removes an attachment was a 16px target in a browser. A real
    box, negative margin so the chip does not grow around it.
  */
  chipRemove: {
    width: tokens.touch.min,
    height: tokens.touch.min,
    alignItems: 'center',
    justifyContent: 'center',
    marginVertical: -10,
    marginRight: -8,
  },
  send: {
    width: tokens.touch.min,
    height: tokens.touch.min,
    borderRadius: tokens.touch.min / 2,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 2,
  },
});
