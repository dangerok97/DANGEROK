import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { api } from '@/src/api/client';
import { useAuth } from '@/src/contexts/AuthContext';
import { AppInput } from '@/src/components/ui/AppInput';
import { AppButton } from '@/src/components/ui/AppButton';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

/** No fabricated preview facts: the map below reads the saved account/profile. */
export function KnowledgeWelcome({ firstRun }: { firstRun: boolean }) {
  const { user, updateUser } = useAuth();
  const { colors } = useTheme();
  const complete = !!(user?.identity_confirmed && user.first_name && user.last_name);
  const [edit, setEdit] = useState(false);
  const [first, setFirst] = useState(user?.first_name || '');
  const [last, setLast] = useState(user?.last_name || '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [show, setShow] = useState(firstRun);
  const tutorial = !user?.knowledge_tutorial_version;
  if (!show && !edit) return <Pressable accessibilityRole="button" onPress={() => { setShow(true); setEdit(!complete); }} style={styles.cue}>
    <Text style={{ color: colors.accent }}>{complete ? 'Nome nelle chiamate e guida alla mappa' : 'Completa nome e cognome per le chiamate'} ↗</Text>
  </Pressable>;
  const save = async () => {
    if (busy) return;
    if (!first.trim() || !last.trim()) { setError('Inserisci sia il nome sia il cognome.'); return; }
    setBusy(true); setError('');
    try {
      const saved = await api.updateIdentity(first.trim(), last.trim(), true);
      updateUser(saved); setEdit(false); setShow(false);
    } catch { setError('Non ho salvato il nome. Controlla i campi e riprova.'); }
    finally { setBusy(false); }
  };
  return <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]} testID="knowledge-welcome">
    <Text accessibilityRole="header" style={[styles.title, { color: colors.textPrimary }]}>{tutorial ? 'La tua mappa comincia da te' : 'Il tuo nome, la tua mappa'}</Text>
    <Text style={[styles.text, { color: colors.textSecondary }]}>1. Ogni informazione salvata diventa una stella. Nome e cognome sono le prime: quando autorizzi una chiamata, ORA si presenta come tua assistente.</Text>
    {complete && !edit ? <>
      <Text style={[styles.text, { color: colors.textPrimary }]}>«Sono ORA, l’assistente di {user?.first_name} {user?.last_name}».</Text>
      <Pressable accessibilityRole="button" onPress={() => setEdit(true)} style={styles.cue}><Text style={{ color: colors.accent }}>Modifica nome e cognome</Text></Pressable>
    </> : <>
      <AppInput label="Nome" accessibilityLabel="Nome per le chiamate" value={first} onChangeText={setFirst} autoCapitalize="words" autoComplete="given-name" textContentType="givenName" editable={!busy} />
      <AppInput label="Cognome" accessibilityLabel="Cognome per le chiamate" value={last} onChangeText={setLast} autoCapitalize="words" autoComplete="family-name" textContentType="familyName" editable={!busy} />
    </>}
    <Text style={[styles.text, { color: colors.textSecondary }]}>2. In VITA, ogni risposta aggiunge punti al ramo corrispondente. Casa aiuta con le incombenze, impegni e lavoro con il tempo, persone con le relazioni. Il ramo si illumina quando le sue informazioni sono complete.</Text>
    <Text style={[styles.text, { color: colors.textSecondary }]}>3. Tocca le stelle per scoprire cosa ORA ricorda e perché. Scegli tu cosa raccontare: puoi saltare le domande e riprenderle più avanti. Anche un «no» è utile, saltare non accende stelle.</Text>
    {error ? <Text accessibilityRole="alert" style={{ color: colors.error }}>{error}</Text> : null}
    <AppButton label={tutorial ? 'Iniziamo dalla mia vita' : 'Salva nome e cognome'} onPress={save} loading={busy} disabled={busy} />
    {!firstRun ? <Pressable accessibilityRole="button" onPress={() => { setShow(false); setEdit(false); }} style={styles.cue}><Text style={{ color: colors.textSecondary }}>Chiudi</Text></Pressable> : null}
  </View>;
}
const styles = StyleSheet.create({
  card: { borderWidth: StyleSheet.hairlineWidth, borderRadius: tokens.radius.lg, padding: 22, gap: 14 },
  title: { fontSize: 23, fontWeight: '600' }, text: { fontSize: 15, lineHeight: 23 },
  cue: { minHeight: 44, justifyContent: 'center', alignSelf: 'flex-start' },
});
