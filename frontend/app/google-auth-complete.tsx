/** Google browser OAuth completion. No ID token or JWT is ever passed in a URL. */
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';

import { api } from '@/src/api/client';
import { useAuth } from '@/src/contexts/AuthContext';
import { routeAfterAuth } from '@/src/life-setup/routeAfterAuth';
import { googleBrowserFailure, GOOGLE_BROWSER_PROOF_KEY, GOOGLE_BROWSER_NEXT_KEY } from '@/src/auth/googleBrowserRedirect';
import { loginHrefFor, safeNextTarget } from '@/src/shell/nextTarget';
import { tokens } from '@/src/theme/tokens';

export default function GoogleAuthComplete() {
  const router = useRouter();
  const { signIn } = useAuth();
  const ran = useRef(false);
  const returnTo = useRef<string | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;

    if (typeof window === 'undefined') {
      setError('Completa l’accesso da un browser.');
      setLoading(false);
      return;
    }
    // Read the one-use ticket from the fragment and remove it BEFORE making
    // any requests or navigating. Browser tab proof stays in sessionStorage.
    const ticket = new URLSearchParams(window.location.hash.replace(/^#/, '')).get('ticket') || '';
    const returnedError = new URLSearchParams(window.location.search).get('error') || '';
    let proof = '';
    let intended: string | null = null;
    try {
      proof = window.sessionStorage.getItem(GOOGLE_BROWSER_PROOF_KEY) || '';
      intended = safeNextTarget(window.sessionStorage.getItem(GOOGLE_BROWSER_NEXT_KEY));
      window.sessionStorage.removeItem(GOOGLE_BROWSER_PROOF_KEY);
      window.sessionStorage.removeItem(GOOGLE_BROWSER_NEXT_KEY);
    } catch {
      // A browser that blocks session storage cannot verify this login flow.
      proof = '';
    }
    returnTo.current = intended;
    window.history.replaceState(window.history.state, '', '/google-auth-complete');

    if (returnedError || !ticket || !proof) {
      setError(googleBrowserFailure(returnedError || 'google_login_unavailable'));
      setLoading(false);
      return;
    }

    void (async () => {
      try {
        const auth = await api.googleBrowserLoginComplete(ticket, proof);
        await signIn(auth.token, auth.user);
        await routeAfterAuth(router, auth.user.user_id, intended);
      } catch {
        setError('L’accesso Google non è stato confermato. Riprova dalla schermata di accesso.');
      } finally {
        setLoading(false);
      }
    })();
  }, [router, signIn]);

  return (
    <View style={styles.screen} testID="google-browser-complete">
      <Text style={styles.wordmark}>ORA</Text>
      <Text style={styles.title}>{loading ? 'Completo l’accesso…' : error ? 'Accesso non completato' : 'Accesso riuscito'}</Text>
      {loading ? (
        <ActivityIndicator color={tokens.color.brand} size="large" />
      ) : error ? (
        <>
          <Text style={styles.message} accessibilityRole="alert">{error}</Text>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Torna alla schermata di accesso"
            testID="google-auth-return-login"
            style={styles.back}
            onPress={() => router.replace(loginHrefFor(returnTo.current) as never)}
          >
            <Text style={styles.backText}>Torna all’accesso</Text>
          </Pressable>
        </>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1, backgroundColor: tokens.color.backgroundPrimary,
    alignItems: 'center', justifyContent: 'center',
    gap: 22, paddingHorizontal: 24,
  },
  wordmark: { color: tokens.color.onSurface, fontSize: 38, fontWeight: '800' },
  title: { color: tokens.color.onSurface, fontSize: 22, fontWeight: '700', textAlign: 'center' },
  message: { color: tokens.color.onSurfaceMuted, fontSize: 15, textAlign: 'center', lineHeight: 22 },
  back: {
    paddingVertical: 14, paddingHorizontal: 22, borderRadius: 12,
    backgroundColor: tokens.color.brand,
  },
  backText: { color: tokens.color.onBrand, fontWeight: '700', fontSize: 15 },
});
