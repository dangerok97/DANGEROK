/**
 * Il menu del «+»: cosa aggiungere alla conversazione.
 *
 *     IL «+» È UNA DOMANDA, NON UN COMANDO.
 *
 * Finora toccarlo apriva dritto il selettore di sistema, e quella era una
 * risposta a una domanda che nessuno aveva fatto: chi vuole scattare una foto
 * si ritrovava a navigare cartelle, chi voleva un PDF si ritrovava fra le
 * immagini. Adesso il «+» chiede prima cosa si vuole aggiungere, e solo dopo
 * apre la cosa giusta.
 *
 * Quattro voci e non una di più. Niente ricerca sul web, niente generazione di
 * immagini, niente Gmail o Calendario: da questo composer quei percorsi non
 * esistono, e una voce che non porta da nessuna parte è peggio di una voce
 * assente — la si tocca una volta, non succede niente, e da lì in poi il menu
 * intero è sospetto.
 *
 * La fotocamera compare soltanto dove si apre davvero. Su un telefono, in un
 * browser, `capture` sull'input apre l'obiettivo; dove non c'è, la voce non
 * c'è, invece di esserci e non fare niente.
 */
import React from 'react';
import { Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

/** Cosa si è scelto di aggiungere. */
export type AttachKind = 'any' | 'photo' | 'camera' | 'document';

type Entry = {
  kind: AttachKind;
  icon: React.ComponentProps<typeof Ionicons>['name'];
  title: string;
  hint: string;
};

/**
 * Se da qui si può aprire l'obiettivo.
 *
 * L'attributo `capture` è una cosa del browser, e su un telefono apre la
 * fotocamera; su un desktop viene ignorato e resta un normale selettore di
 * file, che sarebbe una voce bugiarda. In app nativa servirebbe un modulo che
 * qui non c'è: finché non c'è, la voce non si mostra.
 */
export function cameraOpens(): boolean {
  if (Platform.OS !== 'web') return false;
  if (typeof navigator === 'undefined') return false;
  return /iphone|ipad|ipod|android/i.test(navigator.userAgent || '');
}

export function attachEntries(): Entry[] {
  const all: Entry[] = [
    {
      kind: 'any',
      icon: 'albums-outline',
      title: 'Foto e file',
      hint: 'Carica dal dispositivo',
    },
    {
      kind: 'photo',
      icon: 'image-outline',
      title: 'Foto',
      hint: 'Scegli dalla libreria',
    },
    {
      kind: 'camera',
      icon: 'camera-outline',
      title: 'Fotocamera',
      hint: 'Scatta una foto',
    },
    {
      kind: 'document',
      icon: 'document-text-outline',
      title: 'Documenti',
      hint: 'Aggiungi un documento',
    },
  ];
  return all.filter((e) => e.kind !== 'camera' || cameraOpens());
}

type Props = {
  open: boolean;
  onClose: () => void;
  onChoose: (kind: AttachKind) => void;
  testID: string;
  /**
   * Di quanto stare sopra il pulsante, perché il menu non copra il campo.
   *
   * Il «+» vive in fondo al contenitore dove si scrive, e un menu ancorato a
   * lui si apre davanti alla riga che la persona stava leggendo — misurato:
   * ventidue punti sopra il campo, su telefono e su desktop. La distanza non
   * è fissa perché il contenitore cresce con il testo, quindi la calcola chi
   * quel testo lo misura già.
   */
  lift?: number;
};

export function OraAttachMenu({ open, onClose, onChoose, testID, lift = 52 }: Props) {
  const { colors } = useTheme();

  /*
    Esc chiude. È l'unico modo di uscire che una persona alla tastiera prova
    per primo, e un menu che non risponde a Esc la costringe a cercare col
    mouse un punto vuoto dello schermo.
  */
  React.useEffect(() => {
    if (!open || Platform.OS !== 'web') return;
    if (typeof document === 'undefined') return;
    const onKey = (e: any) => {
      if (e?.key === 'Escape') {
        e.preventDefault?.();
        onClose();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <>
      {/*
        Il velo che raccoglie il tocco fuori. Invisibile apposta: un menu
        piccolo che oscura tutto lo schermo dietro di sé si comporta come una
        finestra modale, e questa non lo è.
      */}
      <Pressable
        /*
          Raccoglie il tocco fuori e nient'altro. Non è un comando: chi
          tabula deve arrivare alla prima voce del menu, non a un rettangolo
          invisibile grande quanto lo schermo, e chi usa un lettore di
          schermo non deve sentirselo annunciare.
        */
        focusable={false}
        // `focusable` da solo non toglie il velo dal giro della tastiera su
        // web: verificato tabulando, ci si finisce comunque. L'attributo del
        // browser sì.
        {...(Platform.OS === 'web' ? ({ tabIndex: -1 } as any) : {})}
        accessibilityElementsHidden
        importantForAccessibility="no-hide-descendants"
        onPress={onClose}
        style={styles.veil}
        testID={`${testID}-veil`}
      />
      <View
        accessibilityRole="menu"
        style={[
          styles.sheet,
          {
            bottom: lift,
            backgroundColor: colors.surfaceElevated || colors.surface,
            borderColor: colors.border,
          },
        ]}
        testID={testID}
      >
        {attachEntries().map((entry) => (
          <Pressable
            key={entry.kind}
            accessibilityRole="menuitem"
            accessibilityLabel={`${entry.title}. ${entry.hint}`}
            onPress={() => {
              onClose();
              onChoose(entry.kind);
            }}
            style={({ pressed, hovered }: any) => [
              styles.row,
              (pressed || hovered) && {
                backgroundColor: colors.backgroundSecondary,
              },
            ]}
            testID={`${testID}-${entry.kind}`}
          >
            <Ionicons name={entry.icon} size={20} color={colors.textSecondary} />
            <View style={styles.words}>
              <Text style={[styles.title, { color: colors.textPrimary }]}>
                {entry.title}
              </Text>
              <Text style={[styles.hint, { color: colors.textTertiary }]}>
                {entry.hint}
              </Text>
            </View>
          </Pressable>
        ))}
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  veil: {
    position: 'absolute',
    top: -4000,
    left: -4000,
    right: -4000,
    bottom: -4000,
  },
  /*
    Ancorato al «+», cioè in basso a sinistra, e aperto verso l'alto: il
    composer sta in fondo allo schermo e un menu che scendesse finirebbe sotto
    la tastiera. `maxWidth` in percentuale perché su un telefono da 390 punti
    una larghezza fissa da desktop uscirebbe dal bordo destro.
  */
  sheet: {
    position: 'absolute',
    left: 0,
    minWidth: 244,
    maxWidth: '92%',
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    paddingVertical: 6,
    overflow: 'hidden',
    ...(Platform.OS === 'web'
      ? { boxShadow: '0 12px 32px rgba(0,0,0,0.10)' as any }
      : {
          shadowColor: '#000',
          shadowOpacity: 0.12,
          shadowRadius: 18,
          shadowOffset: { width: 0, height: 8 },
          elevation: 8,
        }),
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    minHeight: tokens.touch.min,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  words: { flexShrink: 1 },
  title: { fontSize: 15, lineHeight: 20 },
  hint: { fontSize: 12, lineHeight: 16, marginTop: 1 },
});
