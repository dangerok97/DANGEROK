import { useState } from 'react';
import { ScrollView, View } from 'react-native';
import { useRouter } from 'expo-router';
import { ImmersiveScreen } from '@/src/shell';
import { useAuth } from '@/src/contexts/AuthContext';
import { api } from '@/src/api/client';
import { RegistrationIntro } from './RegistrationIntro';

/** First social sign-in / older clients complete the same introduction once. */
export function RegistrationWelcome() {
  const { user, updateUser } = useAuth();
  const router = useRouter();
  const [first, setFirst] = useState(user?.first_name || '');
  const [last, setLast] = useState(user?.last_name || '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const complete = async () => {
    if (busy) return;
    setBusy(true); setError('');
    try { updateUser(await api.updateIdentity(first.trim(), last.trim(), true)); }
    catch { setError('Non ho salvato il nome. Controlla i campi e riprova.'); }
    finally { setBusy(false); }
  };
  return <ImmersiveScreen><ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ flexGrow: 1, padding: 24, paddingBottom: 48, justifyContent: 'center' }}>
    <View style={{ width: '100%', maxWidth: 560, alignSelf: 'center' }}>
      <RegistrationIntro first={first} last={last} onFirstChange={setFirst} onLastChange={setLast} onComplete={complete} onExit={() => router.replace('/ora' as any)} busy={busy} submitError={error} savedIdentity />
    </View>
  </ScrollView></ImmersiveScreen>;
}
