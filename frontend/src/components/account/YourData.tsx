/**
 * I tuoi dati: scaricarli tutti, o eliminare l'account.
 *
 * Fino al 29/10/2026 l'informativa diceva, onestamente, che per andarsene
 * bisognava scrivere all'assistenza. L'App Store, la verifica di Google e il
 * GDPR chiedono che si possa fare da qui. L'eliminazione è immediata e
 * definitiva: per questo chiede di scrivere ELIMINA (e la password, a chi
 * accede con email e password).
 */
import { useState } from 'react';
import { Platform, StyleSheet, Text, TextInput, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import { api } from '@/src/api/client';
import { useAuth } from '@/src/contexts/AuthContext';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { ActionBtn } from '@/src/components/ui/ActionBtn';
import { SettingCard } from '@/src/components/account';
import { humanizeError } from '@/src/utils/errors';

export const DELETE_WORD = 'ELIMINA';

export function canConfirmDeletion(word: string): boolean {
  return word.trim().toUpperCase() === DELETE_WORD;
}

export function YourData() {
  const { colors } = useTheme();
  const router = useRouter();
  const { signOut } = useAuth();
  const [busy, setBusy] = useState<'export' | 'delete' | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const [word, setWord] = useState('');
  const [password, setPassword] = useState('');

  const download = async () => {
    setBusy('export');
    setError(null);
    setMessage(null);
    try {
      const { blob, filename } = await api.exportMyData();
      if (Platform.OS === 'web' && typeof document !== 'undefined') {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 10_000);
        setMessage('File pronto: lo trovi nei download.');
      } else {
        setMessage('Lo scaricamento dei dati per ora è disponibile dalla versione web di ORA.');
      }
    } catch (err) {
      setError(humanizeError(err));
    } finally {
      setBusy(null);
    }
  };

  const erase = async () => {
    if (!canConfirmDeletion(word)) return;
    setBusy('delete');
    setError(null);
    try {
      await api.deleteMyAccount(word.trim().toUpperCase(), password || undefined);
      await signOut();
      router.replace('/login' as never);
    } catch (err) {
      setError(humanizeError(err));
      setBusy(null);
    }
  };

  const input = [styles.input, { borderColor: colors.border, color: colors.textPrimary }];

  return (
    <SettingCard testID="your-data">
      <View style={styles.header}>
        <View style={[styles.icon, { backgroundColor: colors.accentMuted }]}>
          <Ionicons name="shield-checkmark-outline" size={19} color={colors.accent} />
        </View>
        <Text style={[styles.title, { color: colors.textPrimary }]}>I tuoi dati</Text>
      </View>
      <Text style={[styles.description, { color: colors.textSecondary }]}>
        Puoi scaricare tutto quello che ORA ha salvato per te, in un unico file. Password, token di
        accesso e chiavi non sono inclusi.
      </Text>
      <View style={styles.buttons}>
        <ActionBtn icon="download-outline" label="Scarica i miei dati" onPress={() => void download()}
          loading={busy === 'export'} disabled={!!busy} testID="btn-export-data" />
        {!asking ? (
          <ActionBtn variant="danger" icon="trash-outline" label="Elimina account"
            onPress={() => setAsking(true)} disabled={!!busy} testID="btn-delete-account" />
        ) : null}
      </View>

      {asking ? (
        <View style={styles.confirm} testID="delete-confirm">
          <Text style={[styles.description, { color: colors.textPrimary }]}>
            L'eliminazione è immediata e non si può annullare: account, conversazioni, ricordi,
            situazioni, promemoria, documenti, foto e collegamenti vengono cancellati. Le copie di
            sicurezza cifrate spariscono entro 30 giorni. Per confermare scrivi {DELETE_WORD}.
          </Text>
          <TextInput value={word} onChangeText={setWord} placeholder={DELETE_WORD} autoCapitalize="characters"
            autoCorrect={false} style={input} testID="delete-word" accessibilityLabel="Scrivi ELIMINA per confermare" />
          <TextInput value={password} onChangeText={setPassword} secureTextEntry
            placeholder="Password (se accedi con email e password)" style={input} testID="delete-password"
            accessibilityLabel="Password" />
          <View style={styles.buttons}>
            <ActionBtn variant="danger" icon="trash" label="Elimina definitivamente"
              onPress={() => void erase()} loading={busy === 'delete'}
              disabled={!canConfirmDeletion(word) || !!busy} testID="btn-delete-confirm" />
            <ActionBtn icon="close" label="Annulla" onPress={() => { setAsking(false); setWord(''); setPassword(''); }}
              disabled={busy === 'delete'} testID="btn-delete-cancel" />
          </View>
        </View>
      ) : null}

      {message ? <Text style={[styles.description, { color: colors.textSecondary }]}>{message}</Text> : null}
      {error ? <Text accessibilityRole="alert" style={[styles.description, { color: colors.error }]}>{error}</Text> : null}
    </SettingCard>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.md },
  icon: { width: 40, height: 40, borderRadius: tokens.radius.sm, alignItems: 'center', justifyContent: 'center' },
  title: { fontSize: 16, fontWeight: '650' as any },
  description: { fontSize: 13, lineHeight: 19, marginTop: 6 },
  buttons: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 },
  confirm: { marginTop: 12, gap: 8 },
  input: { borderWidth: StyleSheet.hairlineWidth, borderRadius: tokens.radius.sm, paddingHorizontal: 12, minHeight: 44, fontSize: 15 },
});
