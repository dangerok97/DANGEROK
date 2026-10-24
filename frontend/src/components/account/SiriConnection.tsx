/**
 * Siri, through the Shortcuts app.
 *
 * A web app cannot register with Siri, but a shortcut built once in Comandi
 * Rapidi can send what was dictated to ORA and show the answer, which Siri
 * reads aloud. The shortcut carries a personal key: it opens only that door,
 * it is shown once, and making a new one or turning Siri off revokes it.
 */
import { useCallback, useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Clipboard from 'expo-clipboard';

import { api, type SiriKeyStatus } from '@/src/api/client';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { ActionBtn } from '@/src/components/ui/ActionBtn';
import { SettingCard } from '@/src/components/account';
import { humanizeError } from '@/src/utils/errors';

export const SIRI_SHORTCUT_NAME = 'Parla con ORA';

export const SIRI_STEPS: Array<{ title: string; detail: string }> = [
  {
    title: 'Apri Comandi Rapidi',
    detail: 'Sull’iPhone apri l’app Comandi Rapidi e tocca + in alto a destra.',
  },
  {
    title: 'Ascolta cosa dici',
    detail: 'Tocca «Aggiungi azione», cerca «Detta» e scegli «Detta testo».',
  },
  {
    title: 'Manda la frase a ORA',
    detail:
      'Aggiungi l’azione «Ottieni contenuti di URL» e incolla l’indirizzo qui sotto. ' +
      'Tocca la freccia accanto all’azione: Metodo POST. In «Intestazioni» aggiungi ' +
      'la chiave Authorization con il valore copiato da qui. In «Corpo richiesta» ' +
      'scegli JSON, aggiungi un campo Testo con chiave text e, come valore, ' +
      'la variabile «Testo dettato».',
  },
  {
    title: 'Fatti leggere la risposta',
    detail: 'Aggiungi l’azione «Mostra risultato» con «Contenuti dell’URL». Con Siri la risposta viene letta ad alta voce.',
  },
  {
    title: 'Dagli un nome',
    detail: `Rinomina il comando «${SIRI_SHORTCUT_NAME}». Da ora: «Ehi Siri, ${SIRI_SHORTCUT_NAME.toLowerCase()}».`,
  },
];

export const SIRI_LOCATION_TIP =
  'Facoltativo, per le richieste legate a dove sei: prima di «Ottieni contenuti di URL» ' +
  'aggiungi «Ottieni posizione attuale», poi nel corpo JSON aggiungi due campi Numero, ' +
  'latitude e longitude, con Latitudine e Longitudine della posizione.';

function when(iso: string | null): string {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString('it-IT', {
      day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return '';
  }
}

export function SiriConnection() {
  const { colors } = useTheme();
  const [status, setStatus] = useState<SiriKeyStatus | null>(null);
  const [key, setKey] = useState<string | null>(null);
  const [copied, setCopied] = useState<'key' | 'url' | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setStatus(await api.siriKeyStatus());
    } catch (err) {
      setError(humanizeError(err));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const issue = async () => {
    setBusy(true);
    setError(null);
    try {
      const next = await api.siriIssueKey();
      setKey(next.key);
      setStatus({ active: true, created_at: next.created_at, last_used_at: null });
    } catch (err) {
      setError(humanizeError(err));
    } finally {
      setBusy(false);
    }
  };

  const revoke = async () => {
    setBusy(true);
    setError(null);
    try {
      setStatus(await api.siriRevokeKey());
      setKey(null);
    } catch (err) {
      setError(humanizeError(err));
    } finally {
      setBusy(false);
    }
  };

  const copy = async (what: 'key' | 'url') => {
    const value = what === 'key' ? (key ? `Bearer ${key}` : '') : api.siriAskUrl();
    if (!value) return;
    try {
      await Clipboard.setStringAsync(value);
      setCopied(what);
    } catch (err) {
      setError(humanizeError(err));
    }
  };

  const used = when(status?.last_used_at ?? null);

  return (
    <SettingCard testID="siri-connection">
      <View style={styles.header}>
        <View style={[styles.icon, { backgroundColor: colors.accentMuted }]}>
          <Ionicons name="mic-outline" size={19} color={colors.accent} />
        </View>
        <View style={styles.headerText}>
          <Text style={[styles.title, { color: colors.textPrimary }]}>ORA con Siri</Text>
          <Text style={[styles.subtitle, { color: colors.textSecondary }]} testID="siri-status">
            {status?.active
              ? used
                ? `Attivo · ultimo uso ${used}`
                : 'Attivo · non ancora usato'
              : 'Non attivo'}
          </Text>
        </View>
      </View>

      <Text style={[styles.description, { color: colors.textSecondary }]}>
        Di’ «Ehi Siri, {SIRI_SHORTCUT_NAME.toLowerCase()}» e parla: ORA riceve la frase come
        se l’avessi scritta in chat e Siri ti legge la risposta. Se ORA ci mette di più,
        ti arriva una notifica. Quello che chiede una tua conferma resta da confermare
        nell’app.
      </Text>

      {key ? (
        <View style={[styles.codeBox, { borderColor: colors.border }]} testID="siri-key-box">
          <Text style={[styles.description, { color: colors.textSecondary }]}>
            Questa chiave si vede solo ora. Copiala nel comando rapido; se la perdi, ne crei una nuova.
          </Text>
          <View style={styles.buttons}>
            <ActionBtn
              primary
              icon={copied === 'key' ? 'checkmark' : 'copy-outline'}
              label={copied === 'key' ? 'Valore copiato' : 'Copia valore Authorization'}
              onPress={() => void copy('key')}
              testID="btn-siri-copy-key"
            />
            <ActionBtn
              icon={copied === 'url' ? 'checkmark' : 'link-outline'}
              label={copied === 'url' ? 'Indirizzo copiato' : 'Copia indirizzo'}
              onPress={() => void copy('url')}
              testID="btn-siri-copy-url"
            />
          </View>
        </View>
      ) : null}

      <View style={styles.steps} testID="siri-steps">
        {SIRI_STEPS.map((step, i) => (
          <View key={step.title} style={styles.step}>
            <Text style={[styles.stepNum, { color: colors.accent }]}>{i + 1}</Text>
            <View style={styles.stepText}>
              <Text style={[styles.stepTitle, { color: colors.textPrimary }]}>{step.title}</Text>
              <Text style={[styles.description, { color: colors.textSecondary, marginTop: 2 }]}>
                {step.detail}
              </Text>
            </View>
          </View>
        ))}
        <Text style={[styles.description, { color: colors.textSecondary }]}>{SIRI_LOCATION_TIP}</Text>
      </View>

      <View style={styles.buttons}>
        <ActionBtn
          primary={!status?.active}
          icon="key-outline"
          label={status?.active ? 'Crea una nuova chiave' : 'Attiva Siri'}
          onPress={() => void issue()}
          loading={busy}
          testID="btn-siri-issue"
          accessibilityHint={status?.active ? 'La chiave di prima smette di funzionare' : undefined}
        />
        {status?.active ? (
          <ActionBtn
            variant="danger"
            icon="close-circle-outline"
            label="Disattiva Siri"
            onPress={() => void revoke()}
            disabled={busy}
            testID="btn-siri-revoke"
          />
        ) : null}
      </View>

      {error ? <Text style={[styles.description, { color: colors.error }]}>{error}</Text> : null}
    </SettingCard>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.md },
  icon: { width: 40, height: 40, borderRadius: tokens.radius.sm, alignItems: 'center', justifyContent: 'center' },
  headerText: { flex: 1, minWidth: 0, gap: 2 },
  title: { fontSize: 16, fontWeight: '650' as any },
  subtitle: { fontSize: 12, lineHeight: 17 },
  description: { fontSize: 13, lineHeight: 19, marginTop: 6 },
  buttons: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 },
  codeBox: { borderWidth: StyleSheet.hairlineWidth, borderRadius: tokens.radius.md, padding: 14, gap: 4, marginTop: 10 },
  steps: { marginTop: 12, gap: 10 },
  step: { flexDirection: 'row', gap: 10 },
  stepNum: { fontSize: 15, fontWeight: '700', width: 18, textAlign: 'right' },
  stepText: { flex: 1, minWidth: 0 },
  stepTitle: { fontSize: 14, fontWeight: '600' },
});
