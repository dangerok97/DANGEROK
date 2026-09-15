/**
 * La decisione che una commissione ferma sta aspettando.
 *
 *     «SERVE UNA TUA DECISIONE» DEVE AVERE QUALCOSA DIETRO.
 *
 * Fino a ieri quello stato mandava chi leggeva in un'altra schermata a
 * ricominciare la conversazione da capo. Ma la domanda è già stata fatta, la
 * risposta della controparte è già arrivata, e quello che manca è una riga
 * sola: sì, no, o un'altra data. Si risponde qui.
 *
 * Tre scelte e non di più — accetta quello che hanno proposto, proponi
 * un'altra cosa, lascia perdere — perché sono le tre cose che si possono
 * davvero fare, e un quarto pulsante sarebbe una taxonomia invece di una
 * decisione.
 *
 * Il disegno è quello di tutto il resto: filetti invece di riquadri, un peso
 * solo di testo, e colore solo dove qualcosa lo ha guadagnato. L'unica cosa
 * accesa qui è l'attesa, perché finché nessuno risponde non si muove niente.
 */
import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { api, type CallContinuation } from '@/src/api/client';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { humanizeError } from '@/src/utils/errors';

type Props = {
  continuation: CallContinuation;
  /** Quando la decisione è presa: la pagina si ricarica da sé. */
  onDecided: (nextCallId: string) => void;
};

export function DecideContinuation({ continuation, onDecided }: Props) {
  const { colors } = useTheme();
  const [altro, setAltro] = useState(false);
  const [testo, setTesto] = useState('');
  const [inCorso, setInCorso] = useState('');
  const [errore, setErrore] = useState<string | null>(null);

  const rispondi = useCallback(
    async (quale: 'accept' | 'alternative' | 'cancel') => {
      if (inCorso) return;
      setInCorso(quale);
      setErrore(null);
      try {
        const res = await api.decideContinuation(
          continuation.id,
          quale,
          quale === 'alternative' ? testo.trim() : undefined,
        );
        onDecided(res.next_call_id || '');
      } catch (e) {
        setErrore(humanizeError(e));
      } finally {
        setInCorso('');
      }
    },
    [continuation.id, inCorso, testo, onDecided],
  );

  if (!continuation.open) return null;

  const puo = (quale: string) => continuation.can.includes(quale as never);

  return (
    <View style={[styles.box, { borderColor: colors.warning }]}>
      <Text style={[styles.says, { color: colors.textPrimary }]}>
        {continuation.says}
      </Text>

      {/* Perché ORA non ha potuto decidere da sola. Non è una scusa: è il
          motivo, e senza di quello la domanda sembrerebbe un capriccio. */}
      {continuation.why_i_could_not_decide ? (
        <Text style={[styles.why, { color: colors.textSecondary }]}>
          Non potevo decidere da sola: {continuation.why_i_could_not_decide}.
        </Text>
      ) : null}

      {altro ? (
        <View style={styles.altro}>
          <TextInput
            value={testo}
            onChangeText={setTesto}
            autoFocus
            placeholder="Quando andrebbe bene? Es. «giovedì dopo le 15»"
            placeholderTextColor={colors.textTertiary}
            testID="continuation-alternative"
            style={[
              styles.input,
              {
                color: colors.textPrimary,
                borderColor: colors.border,
                backgroundColor: colors.backgroundPrimary,
              },
            ]}
            onSubmitEditing={() => testo.trim() && void rispondi('alternative')}
          />
          <View style={styles.row}>
            <Bottone
              label="Proponi questa"
              testID="continuation-send-alternative"
              disabled={!testo.trim()}
              busy={inCorso === 'alternative'}
              onPress={() => void rispondi('alternative')}
              primary
            />
            <Bottone label="Annulla" onPress={() => setAltro(false)} />
          </View>
        </View>
      ) : (
        <View style={styles.row}>
          {puo('accept') && continuation.proposal ? (
            <Bottone
              label="Va bene così"
              testID="continuation-accept"
              busy={inCorso === 'accept'}
              onPress={() => void rispondi('accept')}
              primary
            />
          ) : null}
          {puo('alternative') ? (
            <Bottone
              label="Propongo un'altra data"
              testID="continuation-other"
              onPress={() => setAltro(true)}
            />
          ) : null}
          {puo('cancel') ? (
            <Bottone
              label="Lascia perdere"
              testID="continuation-cancel"
              busy={inCorso === 'cancel'}
              onPress={() => void rispondi('cancel')}
            />
          ) : null}
        </View>
      )}

      {errore ? (
        <Text style={[styles.why, { color: colors.warning }]}>{errore}</Text>
      ) : null}

      {/*
        La telefonata non parte da sola. Nemmeno adesso.

        Rispondere qui allarga il mandato e prepara la seconda chiamata; perché
        squilli serve ancora il sì esplicito su quella chiamata, come per ogni
        altra. Dirlo prima evita di far credere che premere basti.
      */}
      <Text style={[styles.note, { color: colors.textTertiary }]}>
        Se accetti, preparo la richiamata — poi ti chiedo conferma prima di
        comporre.
      </Text>
    </View>
  );
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
        <ActivityIndicator color={colors.textSecondary} size="small" />
      ) : (
        <Text
          style={[
            styles.btnText,
            {
              color: primary ? colors.textPrimary : colors.textSecondary,
              fontWeight: primary ? '600' : '500',
            },
          ]}
        >
          {label}
        </Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  box: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.md,
    padding: tokens.spacing['16'],
    gap: tokens.spacing['12'],
    marginTop: tokens.spacing['12'],
  },
  says: { fontSize: 16, lineHeight: 23, fontWeight: '600', letterSpacing: -0.2 },
  why: { fontSize: 14, lineHeight: 20 },
  note: { fontSize: 13, lineHeight: 18 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: tokens.spacing['8'] },
  altro: { gap: tokens.spacing['8'] },
  input: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.sm,
    paddingHorizontal: tokens.spacing['12'],
    paddingVertical: 10,
    fontSize: 15,
  },
  btn: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.pill,
    paddingHorizontal: tokens.spacing['16'],
    paddingVertical: 8,
    minHeight: 36,
    justifyContent: 'center',
  },
  btnText: { fontSize: 14 },
});
