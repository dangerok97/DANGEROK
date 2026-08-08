import { useRef, useState } from 'react';
import {
  View,
  Text,
  TextInput,
  StyleSheet,
  Pressable,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as Haptics from 'expo-haptics';
import { Ionicons } from '@expo/vector-icons';
import Animated, { FadeIn } from 'react-native-reanimated';

import { tokens } from '@/src/theme/tokens';
import { api } from '@/src/api/client';
import { useAmbientInset } from '@/src/shell';

const SUGGESTIONS = [
  'Dove ho parcheggiato?',
  'Quanto ho speso per la macchina quest\'anno?',
  'Quando ho cambiato gli pneumatici?',
];

export default function MemoriaScreen() {
  const ambient = useAmbientInset();
  const inputRef = useRef<TextInput>(null);
  const [q, setQ] = useState('');
  const [answer, setAnswer] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const ask = async (question?: string) => {
    const text = (question ?? q).trim();
    if (!text) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    setQ(text);
    setBusy(true);
    setAnswer(null);
    try {
      const r = await api.askMemory(text);
      setAnswer(r.answer);
    } catch (e: any) {
      setAnswer('Non riesco a rispondere adesso. Riprova.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <SafeAreaView edges={['top']} style={styles.root}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView
          contentContainerStyle={[styles.scroll, { paddingBottom: ambient.paddingBottom }]}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.header}>
            <Text style={styles.brand}>MEMORIA</Text>
            <Text style={styles.h1}>Chiedi{'\n'}alla tua memoria.</Text>
          </View>

          <View style={styles.searchWrap}>
            <Ionicons name="search" size={18} color={tokens.color.onSurfaceMuted} />
            <TextInput
              testID="memory-search-input"
              ref={inputRef}
              autoFocus={Platform.OS !== 'web'}
              value={q}
              onChangeText={setQ}
              onSubmitEditing={() => ask()}
              returnKeyType="search"
              placeholder="Dove ho comprato il televisore?"
              placeholderTextColor={tokens.color.onSurfaceMuted}
              style={styles.searchInput}
              keyboardAppearance="dark"
            />
            {q.length > 0 && (
              <Pressable
                testID="memory-clear-button"
                onPress={() => { setQ(''); setAnswer(null); }}
                hitSlop={12}
              >
                <Ionicons name="close-circle" size={18} color={tokens.color.onSurfaceDim} />
              </Pressable>
            )}
          </View>

          {!answer && !busy && (
            <View style={styles.suggestions}>
              <Text style={styles.suggestLabel}>PROVA</Text>
              {SUGGESTIONS.map((s, i) => (
                <Pressable
                  key={s}
                  testID={`memory-suggestion-${i}`}
                  onPress={() => ask(s)}
                  style={({ pressed }) => [styles.suggestChip, pressed && styles.pressed]}
                >
                  <Text style={styles.suggestText}>{s}</Text>
                  <Ionicons name="arrow-forward" size={16} color={tokens.color.onSurfaceMuted} />
                </Pressable>
              ))}
            </View>
          )}

          {busy && (
            <View style={styles.answerBlock}>
              <ActivityIndicator color={tokens.color.onSurfaceMuted} />
              <Text style={styles.thinking}>ORA sta cercando…</Text>
            </View>
          )}

          {answer && !busy && (
            <Animated.View entering={FadeIn.duration(300)} style={styles.answerBlock} testID="memory-answer-block">
              <Text style={styles.answerKicker}>RISPOSTA</Text>
              <Text style={styles.answerText}>{answer}</Text>
            </Animated.View>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: tokens.color.surface },
  scroll: { paddingHorizontal: tokens.spacing.lg, paddingTop: tokens.spacing.sm },
  header: { paddingHorizontal: tokens.spacing.xs, marginBottom: tokens.spacing.xl, gap: tokens.spacing.xs },
  brand: { color: tokens.color.onSurfaceMuted, fontSize: tokens.fs.sm, fontWeight: '700', letterSpacing: 2 },
  h1: { color: tokens.color.onSurface, fontSize: tokens.fs.xxxl, fontWeight: '700', lineHeight: 38, letterSpacing: -0.8 },
  searchWrap: {
    height: 56,
    flexDirection: 'row',
    alignItems: 'center',
    gap: tokens.spacing.sm,
    paddingHorizontal: tokens.spacing.lg,
    borderRadius: tokens.radius.lg,
    backgroundColor: tokens.color.surfaceSecondary,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: tokens.color.border,
  },
  searchInput: {
    flex: 1,
    color: tokens.color.onSurface,
    fontSize: tokens.fs.lg,
  },
  suggestions: { marginTop: tokens.spacing.xl, gap: tokens.spacing.sm },
  suggestLabel: {
    color: tokens.color.onSurfaceMuted,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 1.6,
    marginBottom: tokens.spacing.xs,
  },
  suggestChip: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: tokens.spacing.md,
    paddingHorizontal: tokens.spacing.lg,
    borderRadius: tokens.radius.md,
    backgroundColor: tokens.color.surfaceSecondary,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: tokens.color.border,
  },
  suggestText: { color: tokens.color.onSurface, fontSize: tokens.fs.lg },
  answerBlock: {
    marginTop: tokens.spacing.xl,
    padding: tokens.spacing.lg,
    borderRadius: tokens.radius.lg,
    backgroundColor: tokens.color.surfaceSecondary,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: tokens.color.border,
    gap: tokens.spacing.sm,
  },
  answerKicker: {
    color: tokens.color.onSurfaceMuted,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 1.6,
  },
  answerText: {
    color: tokens.color.onSurface,
    fontSize: tokens.fs.lg,
    lineHeight: 26,
  },
  thinking: {
    color: tokens.color.onSurfaceMuted,
    marginTop: tokens.spacing.sm,
    textAlign: 'center',
    fontSize: tokens.fs.base,
  },
  pressed: { opacity: 0.65 },
});
