import { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  Pressable,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import * as Haptics from 'expo-haptics';
import Animated, { FadeIn } from 'react-native-reanimated';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import { tokens } from '@/src/theme/tokens';
import { api } from '@/src/api/client';

type Mode = 'menu' | 'task' | 'memory';

export default function AggiungiScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [mode, setMode] = useState<Mode>('menu');
  const [title, setTitle] = useState('');
  const [context, setContext] = useState('');
  const [memory, setMemory] = useState('');
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2200);
  };

  const saveTask = async () => {
    if (!title.trim()) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    setBusy(true);
    try {
      await api.createTask({ title: title.trim(), context: context.trim() || undefined, urgency: 6, importance: 6 });
      showToast('Aggiunto. ORA lo ordinerà per te.');
      setTitle(''); setContext(''); setMode('menu');
    } catch {
      showToast('Errore. Riprova.');
    } finally { setBusy(false); }
  };

  const saveMemory = async () => {
    if (!memory.trim()) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    setBusy(true);
    try {
      await api.addMemory(memory.trim());
      showToast('Ricorderò per te.');
      setMemory(''); setMode('menu');
    } catch {
      showToast('Errore. Riprova.');
    } finally { setBusy(false); }
  };

  return (
    <SafeAreaView edges={['top']} style={styles.root}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView
          contentContainerStyle={[styles.scroll, { paddingBottom: 96 + insets.bottom }]}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.header}>
            <Text style={styles.brand}>AGGIUNGI</Text>
            <Text style={styles.h1}>{mode === 'menu' ? 'Cosa vuoi\nsalvare?' : mode === 'task' ? 'Nuova\npriorità.' : 'Nuovo\nricordo.'}</Text>
          </View>

          {mode === 'menu' && (
            <View style={styles.grid}>
              <Pressable
                testID="add-task-tile"
                style={({ pressed }) => [styles.tile, pressed && styles.pressed]}
                onPress={() => { setMode('task'); Haptics.selectionAsync(); }}
              >
                <Ionicons name="flash-outline" size={28} color={tokens.color.onSurface} />
                <Text style={styles.tileTitle}>Priorità</Text>
                <Text style={styles.tileSub}>Qualcosa da risolvere</Text>
              </Pressable>

              <Pressable
                testID="add-memory-tile"
                style={({ pressed }) => [styles.tile, pressed && styles.pressed]}
                onPress={() => { setMode('memory'); Haptics.selectionAsync(); }}
              >
                <Ionicons name="bookmark-outline" size={28} color={tokens.color.onSurface} />
                <Text style={styles.tileTitle}>Ricordo</Text>
                <Text style={styles.tileSub}>Da salvare in memoria</Text>
              </Pressable>

              <Pressable
                testID="add-document-tile"
                style={({ pressed }) => [styles.tile, pressed && styles.pressed]}
                onPress={() => {
                  Haptics.selectionAsync();
                  router.push('/(tabs)/documenti');
                }}
              >
                <Ionicons name="document-text-outline" size={28} color={tokens.color.onSurface} />
                <Text style={styles.tileTitle}>Documento</Text>
                <Text style={styles.tileSub}>Carica un file</Text>
              </Pressable>

              <View style={[styles.tile, styles.tileDisabled]} testID="add-photo-tile">
                <Ionicons name="camera-outline" size={28} color={tokens.color.onSurfaceDim} />
                <Text style={[styles.tileTitle, { color: tokens.color.onSurfaceDim }]}>Foto</Text>
                <Text style={styles.tileSub}>In arrivo</Text>
              </View>
            </View>
          )}

          {mode === 'task' && (
            <View style={styles.form}>
              <TextInput
                testID="add-task-title-input"
                autoFocus
                value={title}
                onChangeText={setTitle}
                placeholder="Cosa devi risolvere?"
                placeholderTextColor={tokens.color.onSurfaceMuted}
                style={styles.input}
                keyboardAppearance="dark"
              />
              <TextInput
                testID="add-task-context-input"
                value={context}
                onChangeText={setContext}
                placeholder="Contesto (opzionale)"
                placeholderTextColor={tokens.color.onSurfaceMuted}
                style={[styles.input, { height: 100, textAlignVertical: 'top', paddingTop: tokens.spacing.md }]}
                multiline
                keyboardAppearance="dark"
              />
              <Pressable
                testID="add-task-save-button"
                onPress={saveTask}
                disabled={busy || !title.trim()}
                style={({ pressed }) => [styles.primaryBtn, (pressed || !title.trim()) && { opacity: 0.7 }]}
              >
                {busy ? <ActivityIndicator color={tokens.color.onBrand} /> : <Text style={styles.primaryText}>Aggiungi</Text>}
              </Pressable>
              <Pressable testID="add-cancel-button" onPress={() => setMode('menu')} hitSlop={12}>
                <Text style={styles.subtle}>← Annulla</Text>
              </Pressable>
            </View>
          )}

          {mode === 'memory' && (
            <View style={styles.form}>
              <TextInput
                testID="add-memory-input"
                autoFocus
                value={memory}
                onChangeText={setMemory}
                placeholder="Es. Ho comprato il televisore da MediaWorld il 12/03. Garanzia 2 anni."
                placeholderTextColor={tokens.color.onSurfaceMuted}
                style={[styles.input, { height: 140, textAlignVertical: 'top', paddingTop: tokens.spacing.md }]}
                multiline
                keyboardAppearance="dark"
              />
              <Pressable
                testID="add-memory-save-button"
                onPress={saveMemory}
                disabled={busy || !memory.trim()}
                style={({ pressed }) => [styles.primaryBtn, (pressed || !memory.trim()) && { opacity: 0.7 }]}
              >
                {busy ? <ActivityIndicator color={tokens.color.onBrand} /> : <Text style={styles.primaryText}>Salva</Text>}
              </Pressable>
              <Pressable onPress={() => setMode('menu')} hitSlop={12}>
                <Text style={styles.subtle}>← Annulla</Text>
              </Pressable>
            </View>
          )}
        </ScrollView>

        {toast && (
          <Animated.View entering={FadeIn.duration(200)} style={[styles.toast, { bottom: insets.bottom + 96 }]}>
            <Text style={styles.toastText} testID="add-toast">{toast}</Text>
          </Animated.View>
        )}
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
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: tokens.spacing.md },
  tile: {
    width: '48%',
    height: 140,
    padding: tokens.spacing.lg,
    borderRadius: tokens.radius.lg,
    backgroundColor: tokens.color.surfaceSecondary,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: tokens.color.border,
    justifyContent: 'space-between',
  },
  tileDisabled: { opacity: 0.55 },
  tileTitle: { color: tokens.color.onSurface, fontSize: tokens.fs.lg, fontWeight: '600' },
  tileSub: { color: tokens.color.onSurfaceMuted, fontSize: tokens.fs.sm },
  form: { gap: tokens.spacing.md },
  input: {
    minHeight: 54,
    borderRadius: tokens.radius.md,
    backgroundColor: tokens.color.surfaceSecondary,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: tokens.color.border,
    color: tokens.color.onSurface,
    paddingHorizontal: tokens.spacing.lg,
    fontSize: tokens.fs.lg,
  },
  primaryBtn: {
    height: 54,
    borderRadius: tokens.radius.md,
    backgroundColor: tokens.color.brand,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: tokens.spacing.sm,
  },
  primaryText: { color: tokens.color.onBrand, fontSize: tokens.fs.lg, fontWeight: '700' },
  subtle: {
    color: tokens.color.onSurfaceMuted,
    textAlign: 'center',
    fontSize: tokens.fs.base,
    paddingVertical: tokens.spacing.sm,
  },
  pressed: { opacity: 0.7 },
  toast: {
    position: 'absolute',
    left: tokens.spacing.lg,
    right: tokens.spacing.lg,
    backgroundColor: tokens.color.brand,
    paddingVertical: tokens.spacing.md,
    paddingHorizontal: tokens.spacing.lg,
    borderRadius: tokens.radius.md,
    alignItems: 'center',
  },
  toastText: { color: tokens.color.onBrand, fontSize: tokens.fs.base, fontWeight: '600' },
});
