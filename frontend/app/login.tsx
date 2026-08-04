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
import * as Haptics from 'expo-haptics';
import { useRouter } from 'expo-router';

import { tokens } from '@/src/theme/tokens';
import { api } from '@/src/api/client';
import { useAuth } from '@/src/contexts/AuthContext';
import {
  googleConfiguredForPlatform,
  appleConfiguredForPlatform,
  notConfiguredMessage,
} from '@/src/auth/providersConfig';
import { useGoogleAuthRequest, promptGoogleSignIn } from '@/src/auth/googleSignIn';
import { signInWithApple, isAppleNativeAvailable } from '@/src/auth/appleSignIn';

type Mode = 'buttons' | 'email';
type Busy = 'google' | 'apple' | 'email' | null;

export default function LoginScreen() {
  const router = useRouter();
  const { signIn, user, loading } = useAuth();
  const [mode, setMode] = useState<Mode>('buttons');
  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState<Busy>(null);
  const [err, setErr] = useState<string | null>(null);
  const [appleNative, setAppleNative] = useState(false);
  const [backendGoogle, setBackendGoogle] = useState<boolean | null>(null);
  const [backendApple, setBackendApple] = useState<boolean | null>(null);

  const [googleRequest, , googlePrompt] = useGoogleAuthRequest();

  useEffect(() => {
    if (!loading && user) router.replace('/(tabs)');
  }, [loading, user, router]);

  useEffect(() => {
    isAppleNativeAvailable().then(setAppleNative).catch(() => setAppleNative(false));
    api.authProviders()
      .then((s) => {
        setBackendGoogle(!!s.google?.configured);
        setBackendApple(!!s.apple?.configured);
      })
      .catch(() => {
        setBackendGoogle(null);
        setBackendApple(null);
      });
  }, []);

  const googleReady = googleConfiguredForPlatform() && backendGoogle !== false;
  const appleReady =
    Platform.OS === 'ios'
      ? appleNative || appleConfiguredForPlatform()
      : appleConfiguredForPlatform() && backendApple !== false;

  const handleGoogle = async () => {
    if (busy) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setErr(null);
    if (!googleConfiguredForPlatform()) {
      setErr(notConfiguredMessage());
      return;
    }
    if (backendGoogle === false) {
      setErr(notConfiguredMessage());
      return;
    }
    if (!googleRequest) {
      setErr(notConfiguredMessage());
      return;
    }
    try {
      setBusy('google');
      const res = await promptGoogleSignIn(googlePrompt);
      if (!res.ok) {
        if (!res.cancelled) setErr(res.error);
        return;
      }
      const auth = await api.authGoogle(res.idToken, res.nonce);
      await signIn(auth.token, auth.user);
      router.replace('/(tabs)');
    } catch (e: any) {
      setErr(e.message || 'Errore Google');
    } finally {
      setBusy(null);
    }
  };

  const handleApple = async () => {
    if (busy) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setErr(null);
    if (!appleReady) {
      setErr(notConfiguredMessage());
      return;
    }
    try {
      setBusy('apple');
      const res = await signInWithApple();
      if (!res.ok) {
        if (!res.cancelled) setErr(res.error);
        return;
      }
      const auth = await api.authApple({
        id_token: res.idToken,
        nonce: res.nonce,
        email: res.email,
        full_name: res.fullName,
      });
      await signIn(auth.token, auth.user);
      router.replace('/(tabs)');
    } catch (e: any) {
      setErr(e.message || 'Errore Apple');
    } finally {
      setBusy(null);
    }
  };

  const handleEmail = async () => {
    if (busy) return;
    setErr(null);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    if (!email || !password) {
      setErr('Inserisci email e password');
      return;
    }
    try {
      setBusy('email');
      const auth = isRegister
        ? await api.register(email, password, name || undefined)
        : await api.login(email, password);
      await signIn(auth.token, auth.user);
      router.replace('/(tabs)');
    } catch (e: any) {
      setErr(e.message || 'Errore');
    } finally {
      setBusy(null);
    }
  };

  const showAppleButton = Platform.OS === 'ios' || appleConfiguredForPlatform();

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
          <View style={styles.identity}>
            <Text style={styles.title} testID="login-title">ORA</Text>
            <Text style={styles.tagline}>Il sistema operativo{'\n'}della tua vita.</Text>
          </View>

          <View style={{ flex: 1 }} />

          <View style={styles.actions}>
            {mode === 'buttons' && (
              <>
                {showAppleButton ? (
                  <Pressable
                    testID="login-apple-button"
                    disabled={!!busy}
                    style={({ pressed }) => [
                      styles.btnLight,
                      (!appleReady || !!busy) && styles.btnDisabled,
                      pressed && styles.pressed,
                    ]}
                    onPress={handleApple}
                  >
                    {busy === 'apple' ? (
                      <ActivityIndicator color={tokens.color.onBrand} />
                    ) : (
                      <>
                        <Ionicons name="logo-apple" size={20} color={tokens.color.onBrand} />
                        <Text style={styles.btnLightText}>Continua con Apple</Text>
                      </>
                    )}
                  </Pressable>
                ) : null}

                <Pressable
                  testID="login-google-button"
                  disabled={!!busy}
                  style={({ pressed }) => [
                    styles.btnDark,
                    (!googleReady || !!busy) && styles.btnDisabled,
                    pressed && styles.pressed,
                  ]}
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
                  disabled={!!busy}
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
  btnDisabled: { opacity: 0.55 },
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
