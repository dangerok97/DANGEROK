/**
 * ORA Login — Quiet Premium V1 (Immersive presentation).
 * Auth logic frozen: same providers, modes, routeAfterAuth / Life Setup gate.
 * Prompt 4.1 — visual polish only.
 */
import { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  useWindowDimensions,
} from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';
import { useRouter } from 'expo-router';

import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { AppButton } from '@/src/components/ui/AppButton';
import { AppInput } from '@/src/components/ui/AppInput';
import { ImmersiveScreen, useReducedMotion } from '@/src/shell';
import { api } from '@/src/api/client';
import { useAuth } from '@/src/contexts/AuthContext';
import {
  googleConfiguredForPlatform,
  appleConfiguredForPlatform,
  notConfiguredMessage,
} from '@/src/auth/providersConfig';
import { useGoogleAuthRequest, promptGoogleSignIn } from '@/src/auth/googleSignIn';
import { signInWithApple, isAppleNativeAvailable } from '@/src/auth/appleSignIn';
import { routeAfterAuth } from '@/src/life-setup/routeAfterAuth';
import { humanizeError } from '@/src/utils/errors';

type Mode = 'buttons' | 'email';
type Busy = 'google' | 'apple' | 'email' | null;

const LOGIN_CONTENT_MAX = 460;
const HEADLINE_MAX = 340;

/** Auth-facing copy — preserve meaning, avoid raw HTTP jargon. */
function authErrorMessage(e: unknown, fallback: string): string {
  const err = e as { status?: number; message?: string; detail?: unknown } | null;
  const status = err?.status;
  const raw = String(err?.message || err?.detail || '').toLowerCase();
  if (status === 401 || raw.includes('invalid credentials') || raw.includes('unauthorized')) {
    return 'Email o password non corretti.';
  }
  if (status === 409 || raw.includes('already') || raw.includes('exists')) {
    return 'Esiste già un account con questa email.';
  }
  if (
    raw.includes('network') ||
    raw.includes('failed to fetch') ||
    raw.includes('offline') ||
    raw.includes('load failed')
  ) {
    return 'Non riesco a collegarmi. Riprova tra poco.';
  }
  const human = humanizeError(err, 'default');
  if (human && !/^\d{3}/.test(human) && !human.toLowerCase().includes('unauthorized')) {
    return human;
  }
  return fallback;
}

function RegisterCue({
  isRegister,
  colors,
  disabled,
  onPress,
  testID,
}: {
  isRegister: boolean;
  colors: { textPrimary: string; textTertiary: string };
  disabled: boolean;
  onPress: () => void;
  testID: string;
}) {
  const label = isRegister ? 'Hai già un account? Accedi' : 'Nuovo? Crea un account';
  return (
    <Pressable
      testID={testID}
      disabled={disabled}
      onPress={onPress}
      hitSlop={8}
      accessibilityRole="button"
      accessibilityLabel={label}
      style={({ pressed }) => [styles.registerCue, pressed && { opacity: 0.72 }]}
    >
      {isRegister ? (
        <Text style={styles.registerCueText}>
          <Text style={{ color: colors.textTertiary }}>Hai già un account? </Text>
          <Text style={[styles.registerCueStrong, { color: colors.textPrimary }]}>Accedi</Text>
        </Text>
      ) : (
        <Text style={styles.registerCueText}>
          <Text style={{ color: colors.textTertiary }}>Nuovo? </Text>
          <Text style={[styles.registerCueStrong, { color: colors.textPrimary }]}>
            Crea un account
          </Text>
        </Text>
      )}
    </Pressable>
  );
}

export default function LoginScreen() {
  const router = useRouter();
  const { colors, typography: type } = useTheme();
  const reducedMotion = useReducedMotion();
  const { width } = useWindowDimensions();
  const isDesktop = width >= tokens.responsive.tabletMax;
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
    if (!loading && user) {
      routeAfterAuth(router, user.user_id).catch(() =>
        router.replace('/life-setup' as any),
      );
    }
  }, [loading, user, router]);

  useEffect(() => {
    isAppleNativeAvailable().then(setAppleNative).catch(() => setAppleNative(false));
    api
      .authProviders()
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
      await routeAfterAuth(router, auth.user.user_id);
    } catch (e: unknown) {
      setErr(authErrorMessage(e, 'Non riusciamo ad accedere con Google. Riprova.'));
    } finally {
      setBusy(null);
    }
  };

  const handleApple = async () => {
    if (busy) return;
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
      await routeAfterAuth(router, auth.user.user_id);
    } catch (e: unknown) {
      setErr(authErrorMessage(e, 'Non riusciamo ad accedere con Apple. Riprova.'));
    } finally {
      setBusy(null);
    }
  };

  const handleEmail = async () => {
    if (busy) return;
    setErr(null);
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
      await routeAfterAuth(router, auth.user.user_id);
    } catch (e: unknown) {
      setErr(
        authErrorMessage(
          e,
          isRegister ? "Non riusciamo a creare l'account. Riprova." : 'Non riusciamo ad accedere. Riprova.',
        ),
      );
    } finally {
      setBusy(null);
    }
  };

  const showAppleButton = Platform.OS === 'ios' || appleConfiguredForPlatform();
  const anyBusy = !!busy;

  const enter = reducedMotion ? undefined : FadeIn.duration(tokens.motion.fadeIn.duration);

  /** Google primary among providers: surface + strong border + textPrimary — never Deep Indigo fill. */
  const googleSurfaceStyle = {
    backgroundColor: colors.surfaceElevated,
    borderColor: colors.borderStrong,
  };

  return (
    <ImmersiveScreen testID="login-immersive">
      <KeyboardAvoidingView
        style={styles.fill}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView
          contentContainerStyle={[
            styles.scroll,
            isDesktop ? styles.scrollDesktop : styles.scrollMobile,
          ]}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <Animated.View
            entering={enter}
            style={[styles.column, isDesktop && styles.columnDesktop]}
          >
            <View style={styles.identity}>
              <Text
                style={[styles.wordmark, { color: colors.textPrimary }]}
                testID="login-title"
                accessibilityRole="header"
              >
                ORA
              </Text>
              <Text
                style={[
                  styles.headline,
                  {
                    color: colors.textPrimary,
                    fontSize: isDesktop ? type.title.fontSize : type.headline.fontSize + 2,
                    lineHeight: isDesktop ? type.title.lineHeight + 4 : type.headline.lineHeight + 4,
                    letterSpacing: isDesktop ? type.title.letterSpacing : -0.35,
                  },
                ]}
                accessibilityRole="header"
              >
                Tutto ciò che conta, nel momento giusto.
              </Text>
              <Text
                style={[
                  styles.supporting,
                  {
                    color: colors.textTertiary,
                    fontSize: type.caption.fontSize,
                    lineHeight: type.caption.lineHeight,
                    letterSpacing: type.caption.letterSpacing,
                  },
                ]}
              >
                Accedi per continuare.
              </Text>
            </View>

            <View style={styles.actions}>
              {mode === 'buttons' && (
                <>
                  <View style={styles.providerCluster}>
                    {showAppleButton ? (
                      <AppButton
                        testID="login-apple-button"
                        label="Continua con Apple"
                        icon="logo-apple"
                        variant="secondary"
                        fullWidth
                        loading={busy === 'apple'}
                        disabled={anyBusy}
                        onPress={handleApple}
                        style={!appleReady ? styles.dimmed : undefined}
                        accessibilityHint={
                          appleReady ? undefined : 'Accesso Apple non configurato in questo ambiente'
                        }
                      />
                    ) : null}

                    <AppButton
                      testID="login-google-button"
                      label="Continua con Google"
                      icon="logo-google"
                      variant="secondary"
                      fullWidth
                      loading={busy === 'google'}
                      disabled={anyBusy}
                      onPress={handleGoogle}
                      style={{
                        ...googleSurfaceStyle,
                        ...(!googleReady ? styles.dimmed : null),
                      }}
                      accessibilityHint={
                        googleReady ? undefined : 'Accesso Google non configurato in questo ambiente'
                      }
                    />
                  </View>

                  <View style={styles.oppureRow} accessibilityElementsHidden importantForAccessibility="no">
                    <View style={[styles.oppureHairline, { backgroundColor: colors.divider }]} />
                    <Text style={[styles.oppureLabel, { color: colors.textTertiary }]}>oppure</Text>
                    <View style={[styles.oppureHairline, { backgroundColor: colors.divider }]} />
                  </View>

                  <Pressable
                    testID="login-email-button"
                    disabled={anyBusy}
                    onPress={() => {
                      setMode('email');
                      setErr(null);
                    }}
                    accessibilityRole="button"
                    accessibilityLabel="Continua con Email"
                    style={({ pressed }) => [
                      styles.emailPath,
                      pressed && { opacity: 0.7 },
                      anyBusy && styles.dimmed,
                    ]}
                  >
                    <Text style={[styles.emailPathLabel, { color: colors.textSecondary }]}>
                      Continua con Email
                    </Text>
                  </Pressable>

                  <RegisterCue
                    testID="login-create-account-cta"
                    isRegister={false}
                    colors={colors}
                    disabled={anyBusy}
                    onPress={() => {
                      setIsRegister(true);
                      setMode('email');
                      setErr(null);
                    }}
                  />
                </>
              )}

              {mode === 'email' && (
                <View style={styles.form}>
                  {isRegister ? (
                    <AppInput
                      testID="login-name-input"
                      label="Nome"
                      placeholder="Nome"
                      value={name}
                      onChangeText={setName}
                      autoCapitalize="words"
                      editable={!anyBusy}
                      returnKeyType="next"
                    />
                  ) : null}
                  <AppInput
                    testID="login-email-input"
                    label="Email"
                    placeholder="Email"
                    value={email}
                    onChangeText={setEmail}
                    autoCapitalize="none"
                    autoCorrect={false}
                    keyboardType="email-address"
                    textContentType="emailAddress"
                    autoComplete="email"
                    editable={!anyBusy}
                    returnKeyType="next"
                  />
                  <AppInput
                    testID="login-password-input"
                    label="Password"
                    placeholder="Password"
                    value={password}
                    onChangeText={setPassword}
                    secureTextEntry
                    textContentType={isRegister ? 'newPassword' : 'password'}
                    autoComplete={isRegister ? 'password-new' : 'password'}
                    editable={!anyBusy}
                    returnKeyType="go"
                    onSubmitEditing={handleEmail}
                  />
                  <AppButton
                    testID="login-submit-button"
                    label={isRegister ? 'Crea account' : 'Accedi'}
                    variant="primary"
                    fullWidth
                    loading={busy === 'email'}
                    disabled={anyBusy}
                    onPress={handleEmail}
                  />
                  <RegisterCue
                    testID="login-toggle-mode"
                    isRegister={isRegister}
                    colors={colors}
                    disabled={anyBusy}
                    onPress={() => {
                      setIsRegister((v) => !v);
                      setErr(null);
                    }}
                  />
                  <Pressable
                    testID="login-back-to-buttons"
                    disabled={anyBusy}
                    onPress={() => {
                      setMode('buttons');
                      setErr(null);
                    }}
                    hitSlop={12}
                    accessibilityRole="button"
                    accessibilityLabel="Indietro"
                    style={styles.backCue}
                  >
                    <Text style={[styles.backLabel, { color: colors.textTertiary }]}>← Indietro</Text>
                  </Pressable>
                </View>
              )}

              <View style={styles.errorSlot} accessibilityLiveRegion="polite">
                {err ? (
                  <Text testID="login-error-text" style={[styles.errText, { color: colors.error }]}>
                    {err}
                  </Text>
                ) : null}
              </View>
            </View>
          </Animated.View>
        </ScrollView>
      </KeyboardAvoidingView>
    </ImmersiveScreen>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  scroll: {
    flexGrow: 1,
    justifyContent: 'center',
    paddingHorizontal: tokens.spacing.xl,
  },
  /** Optical lift: less top padding + more bottom → content sits slightly above center */
  scrollMobile: {
    paddingTop: tokens.spacing.xl,
    paddingBottom: tokens.spacing['64'],
  },
  scrollDesktop: {
    paddingTop: tokens.spacing.lg,
    paddingBottom: tokens.spacing['80'],
  },
  column: {
    width: '100%',
    maxWidth: LOGIN_CONTENT_MAX,
    alignSelf: 'center',
    gap: tokens.spacing['40'],
  },
  columnDesktop: {
    gap: tokens.spacing['48'],
  },
  identity: {
    gap: tokens.spacing.xl,
  },
  wordmark: {
    fontSize: tokens.typography.title.fontSize,
    fontWeight: '700',
    letterSpacing: 1.2,
    lineHeight: tokens.typography.title.lineHeight,
    marginBottom: tokens.spacing.xs,
  },
  headline: {
    fontWeight: '500',
    maxWidth: HEADLINE_MAX,
  },
  supporting: {
    fontWeight: '400',
    marginTop: tokens.spacing.xs,
  },
  actions: {
    gap: tokens.spacing.md,
  },
  providerCluster: {
    gap: tokens.spacing.sm,
  },
  oppureRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: tokens.spacing.sm,
    marginVertical: tokens.spacing.xs,
    minHeight: tokens.spacing.lg,
  },
  oppureHairline: {
    height: StyleSheet.hairlineWidth,
    width: 28,
  },
  oppureLabel: {
    fontSize: tokens.typography.footnote.fontSize,
    lineHeight: tokens.typography.footnote.lineHeight,
    letterSpacing: 0.2,
    fontWeight: '400',
  },
  emailPath: {
    minHeight: tokens.touch.min,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: tokens.spacing.sm,
  },
  emailPathLabel: {
    fontSize: tokens.typography.bodySmall.fontSize,
    lineHeight: tokens.typography.bodySmall.lineHeight,
    fontWeight: '500',
    letterSpacing: -0.1,
  },
  form: {
    gap: tokens.spacing.md,
  },
  registerCue: {
    minHeight: tokens.touch.min,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: tokens.spacing.sm,
  },
  registerCueText: {
    fontSize: tokens.typography.bodySmall.fontSize,
    lineHeight: tokens.typography.bodySmall.lineHeight,
    textAlign: 'center',
  },
  registerCueStrong: {
    fontWeight: '500',
  },
  backCue: {
    minHeight: tokens.touch.min,
    alignItems: 'center',
    justifyContent: 'center',
  },
  backLabel: {
    fontSize: tokens.typography.bodySmall.fontSize,
    textAlign: 'center',
  },
  errorSlot: {
    minHeight: tokens.typography.bodySmall.lineHeight + tokens.spacing.sm,
    justifyContent: 'center',
  },
  errText: {
    fontSize: tokens.typography.bodySmall.fontSize,
    textAlign: 'center',
  },
  dimmed: { opacity: 0.55 },
});
