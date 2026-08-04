import { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  TextInput,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import * as WebBrowser from 'expo-web-browser';
import * as Linking from 'expo-linking';
import * as Haptics from 'expo-haptics';
import { useRouter } from 'expo-router';

import { tokens } from '@/src/theme/tokens';
import { api } from '@/src/api/client';
import { useAuth } from '@/src/contexts/AuthContext';

type Mode = 'buttons' | 'email';

export default function LoginScreen() {
  const router = useRouter();
  const { signIn, user, loading } = useAuth();
  const [mode, setMode] = useState<Mode>('buttons');
  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState<'google' | 'email' | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && user) router.replace('/(tabs)');
  }, [loading, user, router]);

  // Handle web session_id from URL fragment/query (Emergent OAuth web return)
  useEffect(() => {
    if (Platform.OS !== 'web') return;
    // eslint-disable-next-line no-undef
    const win: any = typeof window !== 'undefined' ? window : null;
    if (!win) return;
    const parseSession = (): string | null => {
      const hash: string = win.location?.hash || '';
      const search: string = win.location?.search || '';
      const m1 = hash.match(/session_id=([^&]+)/);
      if (m1) return decodeURIComponent(m1[1]);
      const m2 = search.match(/session_id=([^&]+)/);
      if (m2) return decodeURIComponent(m2[1]);
      return null;
    };
    const sid = parseSession();
    if (!sid) return;
    (async () => {
      try {
        setBusy('google');
        const auth = await api.googleSession(sid);
        await signIn(auth.token, auth.user);
        // clean URL
        win.history.replaceState(null, '', win.location.pathname);
        router.replace('/(tabs)');
      } catch (e: any) {
        setErr(e.message || 'Google sign-in failed');
      } finally {
        setBusy(null);
      }
    })();
  }, [signIn, router]);

  const handleGoogle = async () => {
    // Local Cursor builds do not use the Emergent Google bridge by default.
    // Keep the button, but be honest: email/password is the supported path.
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setErr(
      'Login Google non configurato in locale (integrazione Emergent disabilitata). Usa Continua con Email.'
    );
  };

  const handleEmail = async () => {
    setErr(null);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    if (!email || !password) {
      setErr('Inserisci email e password');
      return;
    }
    try {
      setBusy('email');
      const auth = isRegister ? await api.register(email, password, name || undefined) : await api.login(email, password);
      await signIn(auth.token, auth.user);
      router.replace('/(tabs)');
    } catch (e: any) {
      setErr(e.message || 'Errore');
    } finally {
      setBusy(null);
    }
  };

  return (
    <SafeAreaView style={styles.root} edges={['top', 'bottom']}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView
          contentContainerStyle={styles.scroll}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {/* Top: identity */}
          <View style={styles.identity}>
            <Text style={styles.title} testID="login-title">ORA</Text>
            <Text style={styles.tagline}>Il sistema operativo{'\n'}della tua vita.</Text>
          </View>

          <View style={{ flex: 1 }} />

          {/* Bottom: actions */}
          <View style={styles.actions}>
            {mode === 'buttons' && (
              <>
                <Pressable
                  testID="login-apple-button"
                  style={({ pressed }) => [styles.btnLight, pressed && styles.pressed]}
                  onPress={() => setErr('Login Apple in arrivo. Usa Google o Email.')}
                >
                  <Ionicons name="logo-apple" size={20} color={tokens.color.onBrand} />
                  <Text style={styles.btnLightText}>Continua con Apple</Text>
                </Pressable>

                <Pressable
                  testID="login-google-button"
                  disabled={busy === 'google'}
                  style={({ pressed }) => [styles.btnDark, pressed && styles.pressed]}
                  onPress={handleGoogle}
                >
                  {busy === 'google' ? (
                    <ActivityIndicator color={tokens.color.onSurface} />
                  ) : (
                    <>
                      <Ionicons name="logo-google" size={18} color={tokens.color.onSurface} />
                      <Text style={styles.btnDarkText}>Continua con Google</Text>
                    </>
                  )}
                </Pressable>

                <Pressable
                  testID="login-email-button"
                  style={({ pressed }) => [styles.btnGhost, pressed && styles.pressed]}
                  onPress={() => setMode('email')}
                >
                  <Ionicons name="mail-outline" size={18} color={tokens.color.onSurface} />
                  <Text style={styles.btnDarkText}>Continua con Email</Text>
                </Pressable>
              </>
            )}

            {mode === 'email' && (
              <View style={styles.form}>
                {isRegister && (
                  <TextInput
                    testID="login-name-input"
                    placeholder="Nome"
                    placeholderTextColor={tokens.color.onSurfaceMuted}
                    style={styles.input}
                    value={name}
                    onChangeText={setName}
                    autoCapitalize="words"
                  />
                )}
                <TextInput
                  testID="login-email-input"
                  placeholder="Email"
                  placeholderTextColor={tokens.color.onSurfaceMuted}
                  style={styles.input}
                  value={email}
                  onChangeText={setEmail}
                  autoCapitalize="none"
                  autoCorrect={false}
                  keyboardType="email-address"
                  keyboardAppearance="dark"
                />
                <TextInput
                  testID="login-password-input"
                  placeholder="Password"
                  placeholderTextColor={tokens.color.onSurfaceMuted}
                  style={styles.input}
                  value={password}
                  onChangeText={setPassword}
                  secureTextEntry
                  keyboardAppearance="dark"
                />
                <Pressable
                  testID="login-submit-button"
                  disabled={busy === 'email'}
                  style={({ pressed }) => [styles.btnLight, pressed && styles.pressed]}
                  onPress={handleEmail}
                >
                  {busy === 'email' ? (
                    <ActivityIndicator color={tokens.color.onBrand} />
                  ) : (
                    <Text style={styles.btnLightText}>{isRegister ? 'Crea account' : 'Accedi'}</Text>
                  )}
                </Pressable>
                <Pressable
                  testID="login-toggle-mode"
                  onPress={() => { setIsRegister((v) => !v); setErr(null); }}
                  hitSlop={12}
                >
                  <Text style={styles.subtleLink}>
                    {isRegister ? 'Hai già un account? Accedi' : 'Nuovo? Crea un account'}
                  </Text>
                </Pressable>
                <Pressable testID="login-back-to-buttons" onPress={() => { setMode('buttons'); setErr(null); }} hitSlop={12}>
                  <Text style={styles.subtleLink}>← Indietro</Text>
                </Pressable>
              </View>
            )}

            {err && (
              <Text testID="login-error-text" style={styles.errText}>
                {err}
              </Text>
            )}
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: tokens.color.surface },
  scroll: { flexGrow: 1, paddingHorizontal: tokens.spacing.xl, paddingTop: 64, paddingBottom: tokens.spacing.xl },
  identity: { gap: tokens.spacing.md, marginTop: tokens.spacing.xxl },
  title: { color: tokens.color.onSurface, fontSize: tokens.fs.display, fontWeight: '700', letterSpacing: -1 },
  tagline: { color: tokens.color.onSurfaceMuted, fontSize: tokens.fs.lg, lineHeight: 22 },
  actions: { gap: tokens.spacing.md },
  btnLight: {
    height: 54,
    borderRadius: tokens.radius.md,
    backgroundColor: tokens.color.brand,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: tokens.spacing.sm,
  },
  btnLightText: { color: tokens.color.onBrand, fontSize: tokens.fs.lg, fontWeight: '600' },
  btnDark: {
    height: 54,
    borderRadius: tokens.radius.md,
    backgroundColor: tokens.color.surfaceSecondary,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: tokens.color.border,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: tokens.spacing.sm,
  },
  btnGhost: {
    height: 54,
    borderRadius: tokens.radius.md,
    backgroundColor: 'transparent',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: tokens.color.border,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: tokens.spacing.sm,
  },
  btnDarkText: { color: tokens.color.onSurface, fontSize: tokens.fs.lg, fontWeight: '500' },
  pressed: { opacity: 0.6 },
  form: { gap: tokens.spacing.md },
  input: {
    height: 52,
    borderRadius: tokens.radius.md,
    backgroundColor: tokens.color.surfaceSecondary,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: tokens.color.border,
    color: tokens.color.onSurface,
    paddingHorizontal: tokens.spacing.lg,
    fontSize: tokens.fs.lg,
  },
  subtleLink: {
    color: tokens.color.onSurfaceMuted,
    fontSize: tokens.fs.base,
    textAlign: 'center',
    paddingVertical: tokens.spacing.sm,
  },
  errText: {
    color: tokens.color.error,
    fontSize: tokens.fs.base,
    textAlign: 'center',
    paddingTop: tokens.spacing.sm,
  },
});
