import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { api, type AuthIdentitiesResponse } from '@/src/api/client';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { humanizeError } from '@/src/utils/errors';
import { haptic } from '@/src/utils/haptic';
import { useGoogleAuth } from '@/src/auth/googleAuth';
import { signInWithApple } from '@/src/auth/appleSignIn';
import {
  appleConfiguredForPlatform,
  googleConfiguredForPlatform,
  notConfiguredMessage,
} from '@/src/auth/providersConfig';
import type { GoogleAuthResult } from '@/src/auth/googleAuth.types';

import { LAST_METHOD_REFUSAL } from './accountModel';

/**
 * The ways into this account.
 *
 * Lifted out of the old settings page unchanged in behaviour — the same link,
 * unlink and provider-availability calls, the same official Google button host
 * on web. What changed is where it sits and what it is called: signing in is
 * not a "connected service", and putting it beside Google Calendar was the
 * thing that made the old screen ambiguous about what Google could see.
 *
 * The one rule the backend enforces and this repeats in words: you cannot
 * remove the last way in.
 */
export function AuthMethods({
  identities,
  onChanged,
}: {
  identities: AuthIdentitiesResponse | null;
  onChanged: () => void | Promise<void>;
}) {
  const { colors } = useTheme();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const googleAuth = useGoogleAuth();
  const renderGoogleButton = googleAuth.renderButton;
  const googleHost = useRef<View | null>(null);

  const handleGoogleLinkResult = useCallback(
    async (result: GoogleAuthResult) => {
      if (!result.ok) {
        if (!result.cancelled) setError(result.safeMessage);
        return;
      }
      setBusy('link_google');
      try {
        await api.linkGoogle(result.idToken, result.nonce);
        await onChanged();
      } catch (e: any) {
        setError(humanizeError(e));
      } finally {
        setBusy(null);
      }
    },
    [onChanged],
  );

  // On web, Google requires its own rendered button; the host div only exists
  // while Google is unlinked, so the effect re-runs when that changes.
  useEffect(() => {
    if (
      Platform.OS !== 'web' ||
      identities?.methods.google.linked !== false ||
      googleAuth.availability.status !== 'ready' ||
      !renderGoogleButton
    ) return;
    const host = googleHost.current as unknown as HTMLElement | null;
    if (!host) return;
    renderGoogleButton(host, (result) => {
      void handleGoogleLinkResult(result);
    }, { width: 210 }).catch(() => {
      setError('Accesso con Google non disponibile in questo momento.');
    });
  }, [
    googleAuth.availability.status,
    handleGoogleLinkResult,
    identities?.methods.google.linked,
    renderGoogleButton,
  ]);

  const unlink = useCallback(
    async (provider: 'google' | 'apple', allowed: boolean) => {
      if (!allowed) {
        setError(LAST_METHOD_REFUSAL);
        return;
      }
      haptic('warning');
      setBusy(`unlink_${provider}`);
      setError(null);
      try {
        await api.unlinkProvider(provider);
        await onChanged();
      } catch (e: any) {
        setError(humanizeError(e));
      } finally {
        setBusy(null);
      }
    },
    [onChanged],
  );

  const linkGoogle = useCallback(async () => {
    if (googleAuth.availability.status !== 'ready' || !googleConfiguredForPlatform()) {
      setError(googleAuth.availability.safeMessage || notConfiguredMessage());
      return;
    }
    haptic('tap');
    setBusy('link_google');
    setError(null);
    try {
      const res = await googleAuth.signIn();
      if (!res.ok) {
        if (!res.cancelled) setError(res.safeMessage);
        return;
      }
      await api.linkGoogle(res.idToken, res.nonce);
      await onChanged();
    } catch (e: any) {
      setError(humanizeError(e));
    } finally {
      setBusy(null);
    }
  }, [googleAuth, onChanged]);

  const linkApple = useCallback(async () => {
    haptic('tap');
    setBusy('link_apple');
    setError(null);
    try {
      const res = await signInWithApple();
      if (!res.ok) {
        if (!res.cancelled) setError(res.error);
        return;
      }
      await api.linkApple({ id_token: res.idToken, nonce: res.nonce });
      await onChanged();
    } catch (e: any) {
      setError(humanizeError(e));
    } finally {
      setBusy(null);
    }
  }, [onChanged]);

  if (!identities) {
    return (
      <Text style={[styles.note, { color: colors.textTertiary }]} testID="auth-methods-unavailable">
        Non riesco a leggere i tuoi metodi di accesso in questo momento.
      </Text>
    );
  }

  const appleOfferable = Platform.OS === 'ios' || appleConfiguredForPlatform();

  return (
    <View style={styles.wrap} testID="account-auth-methods">
      {/*
        Only when it exists. ORA has no endpoint that sets a password on an
        account that signed up with Google, so an "Email e password — non
        collegato" row would be a permanent statement with nothing behind it.
        This section is the ways in that you have.
      */}
      {identities.methods.password.linked ? (
        <MethodRow
          icon="mail-outline"
          label="Email e password"
          linked
          detail={identities.methods.password.email || identities.email}
          first
        />
      ) : null}
      <MethodRow
        icon="logo-google"
        label="Google"
        linked={identities.methods.google.linked}
        detail={identities.methods.google.email}
        actionLabel={
          identities.methods.google.linked
            ? identities.can_unlink.google
              ? 'Scollega'
              : undefined
            : Platform.OS === 'web'
              ? undefined
              : 'Collega'
        }
        actionSlot={
          !identities.methods.google.linked && Platform.OS === 'web' ? (
            <View ref={googleHost} style={styles.googleHost} />
          ) : undefined
        }
        first={!identities.methods.password.linked}
        busy={busy === 'link_google' || busy === 'unlink_google'}
        onAction={() =>
          identities.methods.google.linked
            ? void unlink('google', identities.can_unlink.google)
            : void linkGoogle()
        }
        // The last remaining way in cannot be removed; saying so where the
        // button would have been is kinder than letting someone press it.
        note={
          identities.methods.google.linked && !identities.can_unlink.google
            ? LAST_METHOD_REFUSAL
            : undefined
        }
      />
      {identities.methods.apple.linked || appleOfferable ? (
        <MethodRow
          icon="logo-apple"
          label="Apple"
          linked={identities.methods.apple.linked}
          detail={identities.methods.apple.email}
          actionLabel={
            identities.methods.apple.linked
              ? identities.can_unlink.apple
                ? 'Scollega'
                : undefined
              : 'Collega'
          }
          busy={busy === 'link_apple' || busy === 'unlink_apple'}
          onAction={() =>
            identities.methods.apple.linked
              ? void unlink('apple', identities.can_unlink.apple)
              : void linkApple()
          }
          note={
            identities.methods.apple.linked && !identities.can_unlink.apple
              ? LAST_METHOD_REFUSAL
              : undefined
          }
        />
      ) : null}

      {error ? (
        <Text style={[styles.error, { color: colors.error }]} testID="auth-methods-error">
          {error}
        </Text>
      ) : null}
    </View>
  );
}

function MethodRow({
  icon,
  label,
  linked,
  detail,
  actionLabel,
  actionSlot,
  onAction,
  busy,
  note,
  first,
}: {
  icon: React.ComponentProps<typeof Ionicons>['name'];
  label: string;
  linked: boolean;
  detail?: string | null;
  actionLabel?: string;
  actionSlot?: React.ReactNode;
  onAction?: () => void;
  busy?: boolean;
  note?: string;
  first?: boolean;
}) {
  const { colors } = useTheme();
  return (
    <View
      style={[
        styles.row,
        !first && { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.divider },
      ]}
      testID={`auth-method-${label.toLowerCase().split(' ')[0]}`}
    >
      <Ionicons name={icon} size={18} color={linked ? colors.textPrimary : colors.textTertiary} />
      <View style={styles.rowBody}>
        <Text style={[styles.rowLabel, { color: colors.textPrimary }]}>{label}</Text>
        <Text style={[styles.rowDetail, { color: colors.textSecondary }]} numberOfLines={1}>
          {linked ? detail || 'Collegato' : 'Non collegato'}
        </Text>
        {note ? <Text style={[styles.rowNote, { color: colors.textTertiary }]}>{note}</Text> : null}
      </View>
      {busy ? (
        <ActivityIndicator size="small" color={colors.textSecondary} />
      ) : actionLabel && onAction ? (
        <Pressable
          onPress={onAction}
          style={({ pressed }) => [styles.action, pressed && styles.pressed]}
          accessibilityRole="button"
          accessibilityLabel={`${actionLabel} ${label}`}
        >
          <Text style={[styles.actionLabel, { color: colors.accent }]}>{actionLabel}</Text>
        </Pressable>
      ) : null}
      {actionSlot}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginTop: 4 },
  row: {
    flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.md,
    minHeight: 64, paddingVertical: tokens.spacing.sm,
  },
  rowBody: { flex: 1, minWidth: 0, gap: 2 },
  rowLabel: { fontSize: 14, fontWeight: '600' },
  rowDetail: { fontSize: 12, lineHeight: 17 },
  rowNote: { fontSize: 12, lineHeight: 17, marginTop: 2 },
  action: {
    minHeight: tokens.touch.min, justifyContent: 'center',
    paddingHorizontal: tokens.spacing.sm,
  },
  actionLabel: { fontSize: 13, fontWeight: '600' },
  googleHost: { width: 210, minHeight: tokens.touch.min },
  note: { fontSize: 13, lineHeight: 19 },
  error: { fontSize: 13, lineHeight: 19, marginTop: tokens.spacing.sm },
  pressed: { opacity: 0.75 },
});
