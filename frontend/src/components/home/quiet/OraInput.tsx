/**
 * Universal Capture / Ask Bar — Apple Search calm, never chat chrome.
 * Production entry → AI Core via /ora (not Conversation Engine / Action Engine).
 */
import { useEffect, useState } from 'react';
import {
  View, Text, TextInput, Pressable, StyleSheet, ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { triggerHaptic } from '@/src/theme/haptics';
import { humanizeError } from '@/src/utils/errors';
import { startOraConversation } from '@/src/ora/startOraConversation';

type Props = {
  onError?: (msg: string) => void;
  /** Ambient ORA tab vs Home ask bar */
  entryPoint?: 'home' | 'ora';
  suggestedText?: string;
};

export function OraInput({ onError, entryPoint = 'home', suggestedText }: Props) {
  const { colors, isDark } = useTheme();
  const router = useRouter();
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (suggestedText) setText(suggestedText); }, [suggestedText]);
  const canSend = Boolean(text.trim()) && !busy;

  const submit = async (origin: 'home' | 'voice' = 'home') => {
    const t = text.trim();
    if (!t || busy) return;
    setBusy(true);
    setError(null);
    try {
      void triggerHaptic('selection');
      await startOraConversation(router, {
        text: t,
        entryPoint,
        origin: origin === 'voice' ? 'voice' : 'home',
      });
      setText('');
      void triggerHaptic('success');
      // busy stays true until unmount / navigation; reset if still mounted
      setBusy(false);
    } catch (e: any) {
      void triggerHaptic('error');
      const message = humanizeError(e, 'default');
      setError(message);
      onError?.(message);
      setBusy(false);
    }
  };

  return (
    <View style={styles.wrap} testID="parla-con-ora">
      <View
        style={[
          styles.row,
          {
            backgroundColor: colors.surface,
            borderColor: colors.border,
          },
        ]}
      >
        <View style={styles.iconBtn} accessibilityElementsHidden>
          <Ionicons name="sparkles-outline" size={18} color={colors.textTertiary} />
        </View>
        <TextInput
          testID="parla-input"
          value={text}
          onChangeText={setText}
          placeholder="Raccontami cosa hai in mente…"
          placeholderTextColor={colors.placeholder}
          style={[styles.input, { color: colors.textPrimary }]}
          editable={!busy}
          returnKeyType="send"
          onSubmitEditing={() => void submit('home')}
          keyboardAppearance={isDark ? 'dark' : 'light'}
          accessibilityLabel="Scrivi a ORA"
        />
        <Pressable
          testID="parla-send"
          accessibilityLabel="Invia a ORA"
          accessibilityRole="button"
          style={({ pressed }) => [
            styles.send,
            {
              backgroundColor: canSend ? colors.accent : colors.backgroundSecondary,
              opacity: pressed ? 0.85 : 1,
            },
          ]}
          onPress={() => void submit('home')}
          disabled={!canSend}
        >
          {busy ? (
            <ActivityIndicator color={colors.accent} size="small" />
          ) : (
            <Ionicons
              name="arrow-up"
              size={18}
              color={canSend ? colors.onAccent : colors.textTertiary}
            />
          )}
        </Pressable>
      </View>
      {error ? (
        <Text accessibilityRole="alert" style={[styles.hint, { color: colors.error }]} testID="parla-error">
          {error}
        </Text>
      ) : null}
    </View>
  );
}

export const ParlaConOra = OraInput;

const styles = StyleSheet.create({
  wrap: { gap: tokens.spacing.xs },
  /*
    PX1.2 — a real, defined surface. The previous 6%-alpha hairline made the
    composer read as disabled chrome sitting at the bottom of the page rather
    than the one place you can say something. It stays quiet — it just stops
    apologising for being there.
  */
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    borderRadius: tokens.radius.full,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: tokens.spacing.md,
    paddingVertical: 4,
    minHeight: 56,
  },
  iconBtn: {
    width: tokens.touch.min,
    height: tokens.touch.min,
    borderRadius: tokens.radius.full,
    alignItems: 'center',
    justifyContent: 'center',
  },
  input: {
    flex: 1,
    minHeight: 48,
    fontSize: tokens.typography.body.fontSize,
    paddingVertical: 10,
    letterSpacing: -0.2,
  },
  send: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  hint: {
    fontSize: tokens.typography.footnote.fontSize,
    lineHeight: 14,
    paddingHorizontal: tokens.spacing.md,
  },
});
