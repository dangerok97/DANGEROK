import { useState } from 'react';
import { ScrollView, View } from 'react-native';
import { useRouter } from 'expo-router';
import { ImmersiveScreen } from '@/src/shell';
import { useAuth } from '@/src/contexts/AuthContext';
import { RegistrationIntro } from '@/src/life-setup/RegistrationIntro';

/** Replay the same registration introduction without changing saved identity. */
export default function WelcomePreview() {
  const router = useRouter();
  const { user } = useAuth();
  const [first, setFirst] = useState(user?.first_name || '');
  const [last, setLast] = useState(user?.last_name || '');
  const finish = () => router.replace('/vita' as any);
  return <ImmersiveScreen>
    <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ flexGrow: 1, padding: 24, paddingBottom: 48, justifyContent: 'center' }}>
      <View style={{ width: '100%', maxWidth: 560, alignSelf: 'center' }}>
        <RegistrationIntro first={first} last={last} onFirstChange={setFirst} onLastChange={setLast} onComplete={finish} onExit={finish} preview />
      </View>
    </ScrollView>
  </ImmersiveScreen>;
}
