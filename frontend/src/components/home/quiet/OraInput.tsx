/**
 * Universal Capture / Ask Bar — Apple Search calm, never chat chrome.
 * Production entry → AI Core via /ora (not Conversation Engine / Action Engine).
 */
import { useState } from 'react';
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
};

export function OraInput({ onError, entryPoint = 'home' }: Props) {
  const { colors, isDark } = useTheme();
  const router = useRouter();
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [voiceHint, setVoiceHint] = useState<string | null>(null);
  const canSend = Boolean(text.trim()) && !busy;

  const submit = async (origin: 'home' | 'voice' = 'home') => {
    const t = text.trim();
    if (!t || busy) return;
    setBusy(true);
    setVoiceHint(null);
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
      onError?.(humanizeError(e, 'default'));
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
            borderColor: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(28,28,30,0.06)',
          },
        ]}
      >
        <Pressable
          testID="parla-mic"
          accessibilityLabel="Voce (riconoscimento non ancora attivo — usa il testo)"
          accessibilityRole="button"
          style={({ pressed }) => [
            styles.iconBtn,
            { opacity: pressed ? 0.55 : 0.72 },
          ]}
          onPress={() => {
            void triggerHaptic('selection');
            setVoiceHint(
              'Voce pronta nella struttura: per ora digita il testo — stesso motore, niente STT.',
            );
            if (text.trim()) void submit('voice');
          }}
          disabled={busy}
        >
          <Ionicons name="mic-outline" size={18} color={colors.textTertiary} />
        </Pressable>
        <TextInput
          testID="parla-input"
          value={text}
          onChangeText={setText}
          placeholder="Cosa vuoi raccontare a ORA…"
          placeholderTextColor={colors.placeholder}
          style={[styles.input, { color: colors.textPrimary }]}
          editable={!busy}
          returnKeyType="send"
          onSubmitEditing={() => void submit('home')}
          keyboardAppearance={isDark ? 'dark' : 'light'}
          accessibilityLabel="Scrivi o parla con ORA"
        />
        <Pressable
          testID="parla-send"
          accessibilityLabel="Invia a ORA"
          accessibilityRole="button"
          style={({ pressed }) => [
            styles.send,
            {
              backgroundColor: canSend ? colors.accentMuted : 'transparent',
              opacity: !canSend ? 0.35 : pressed ? 0.8 : 1,
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
              color={canSend ? colors.accent : colors.textTertiary}
            />
          )}
        </Pressable>
      </View>
      {voiceHint ? (
        <Text style={[styles.hint, { color: colors.textTertiary }]} testID="parla-voice-stub-hint">
          {voiceHint}
        </Text>
      ) : null}
    </View>
  );
}

export const ParlaConOra = OraInput;

const styles = StyleSheet.create({
  wrap: { gap: tokens.spacing.xs },
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
