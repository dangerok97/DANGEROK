/**
 * Memory clarification — Focus shell.
 * ORA asks a natural doubt; user answers freely. Not a DB editor. Not AE chips.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';

import { api, MemoryClarifySession } from '@/src/api/client';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import {
  FocusScreen,
  FOCUS_DECISION_MAX_WIDTH,
} from '@/src/shell';
import { humanizeError } from '@/src/utils/errors';
import { haptic } from '@/src/utils/haptic';

export default function MemoryClarifyScreen() {
  const { sessionId } = useLocalSearchParams<{ sessionId: string }>();
  const router = useRouter();
  const { colors, isDark } = useTheme();
  const [session, setSession] = useState<MemoryClarifySession | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState('');

  const load = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.lifeMemoryClarifyGet(sessionId);
      setSession(res.session);
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    void load();
  }, [load]);

  const onSubmit = useCallback(async () => {
    const answer = text.trim();
    if (!sessionId || !answer || busy) return;
    setBusy(true);
    setError(null);
    void haptic('tap');
    try {
      const res = await api.lifeMemoryClarifyAnswer(sessionId, answer);
      if (res.error === 'gemini_unavailable' || (res.ok === false && res.message)) {
        setError(res.message || 'Non riesco a interpretare la risposta adesso. Riprova.');
        setBusy(false);
        return;
      }
      if (res.needs_followup && res.session) {
        setSession(res.session);
        setText('');
        setBusy(false);
        return;
      }
      // Success — back to Memoria (refetch on focus)
      router.replace('/(tabs)/memoria' as any);
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
      setBusy(false);
    }
  }, [sessionId, text, busy, router]);

  const question = session?.question || session?.followup_question || '';

  return (
    <FocusScreen
      testID="memory-clarify-screen"
      maxWidth={FOCUS_DECISION_MAX_WIDTH}
      chrome={{
        leading: 'close',
        contextLabel: 'Chiarimento',
        onLeadingPress: () => router.back(),
        leadingAccessibilityLabel: 'Chiudi',
      }}
    >
      {loading ? (
        <ActivityIndicator color={colors.textTertiary} style={{ marginTop: 40 }} />
      ) : error && !session ? (
        <Text style={[styles.error, { color: colors.textSecondary }]}>{error}</Text>
      ) : (
        <View style={styles.body}>
          {session?.belief_statement ? (
            <Text style={[styles.belief, { color: colors.textTertiary }]}>
              {session.belief_statement}
            </Text>
          ) : null}
          <Text style={[styles.question, { color: colors.textPrimary }]}>{question}</Text>
          <TextInput
            value={text}
            onChangeText={setText}
            placeholder="Rispondi con le tue parole…"
            placeholderTextColor={colors.textTertiary}
            style={[
              styles.input,
              {
                color: colors.textPrimary,
                borderBottomColor: colors.divider,
                backgroundColor: isDark ? 'transparent' : 'transparent',
              },
            ]}
            multiline
            autoFocus
            editable={!busy}
            testID="memory-clarify-input"
          />
          {error ? (
            <Text style={[styles.error, { color: colors.textSecondary }]}>{error}</Text>
          ) : null}
          <Pressable
            onPress={onSubmit}
            disabled={busy || !text.trim()}
            style={({ pressed }) => [
              styles.cta,
              {
                opacity: busy || !text.trim() ? 0.4 : pressed ? 0.7 : 1,
              },
            ]}
            accessibilityRole="button"
            accessibilityLabel="Invia risposta"
            testID="memory-clarify-submit"
          >
            {busy ? (
              <ActivityIndicator color={colors.textPrimary} />
            ) : (
              <Text style={[styles.ctaText, { color: colors.textPrimary }]}>Continua</Text>
            )}
          </Pressable>
        </View>
      )}
    </FocusScreen>
  );
}

const styles = StyleSheet.create({
  body: {
    paddingTop: tokens.spacing.xl,
    gap: tokens.spacing.lg,
  },
  belief: {
    fontSize: tokens.typography.caption.fontSize,
    lineHeight: tokens.typography.caption.lineHeight,
  },
  question: {
    fontSize: tokens.typography.headline.fontSize,
    fontWeight: tokens.typography.headline.fontWeight,
    lineHeight: tokens.typography.headline.lineHeight,
    letterSpacing: -0.3,
  },
  input: {
    minHeight: 88,
    fontSize: tokens.typography.body.fontSize,
    lineHeight: tokens.typography.body.lineHeight,
    borderBottomWidth: StyleSheet.hairlineWidth,
    paddingVertical: tokens.spacing.md,
    textAlignVertical: 'top',
  },
  cta: {
    alignSelf: 'flex-start',
    marginTop: tokens.spacing.md,
    paddingVertical: tokens.spacing.sm,
  },
  ctaText: {
    fontSize: tokens.typography.body.fontSize,
    fontWeight: '600',
    letterSpacing: -0.2,
  },
  error: {
    fontSize: tokens.typography.caption.fontSize,
    lineHeight: tokens.typography.caption.lineHeight,
  },
});
