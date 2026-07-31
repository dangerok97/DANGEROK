/**
 * DocumentActionsBar — Iterazione 23.
 * Barra orizzontale scrollabile con le azioni derivate dai resolved_fields.
 * Compare solo se `actions.length > 0`. Nessuna azione automatica.
 */
import React, { useCallback, useMemo, useState } from 'react';
import {
  Platform, Pressable, ScrollView, StyleSheet, Text, View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Animated, { FadeIn, FadeOut } from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
import { tokens } from '@/src/theme/tokens';
import type { DocumentInsights } from '@/src/api/client';
import {
  buildDocumentActions,
  runDocumentAction,
  type DocumentAction,
} from '@/src/utils/document_actions';

type Props = { insights: DocumentInsights };

export function DocumentActionsBar({ insights }: Props) {
  const actions = useMemo(() => buildDocumentActions(insights), [insights]);
  const [toast, setToast] = useState<{ text: string; kind: 'success' | 'error' } | null>(null);
  const [runningKind, setRunningKind] = useState<string | null>(null);

  const onToast = useCallback((text: string, kind: 'success' | 'error' = 'success') => {
    setToast({ text, kind });
    setTimeout(() => setToast(null), 2400);
  }, []);

  const onPress = useCallback(async (a: DocumentAction) => {
    if (runningKind) return;
    setRunningKind(a.kind);
    try {
      if (Platform.OS !== 'web') {
        try { await Haptics.selectionAsync(); } catch {}
      }
      await runDocumentAction(a, onToast);
    } finally {
      setRunningKind(null);
    }
  }, [onToast, runningKind]);

  if (!actions.length) return null;

  return (
    <View style={styles.card} accessibilityRole="toolbar" accessibilityLabel="Azioni disponibili">
      <Text style={styles.title}>AZIONI DISPONIBILI</Text>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.row}
        testID="document-actions-bar"
      >
        {actions.map((a) => (
          <Pressable
            key={`${a.kind}-${a.priority}`}
            onPress={() => onPress(a)}
            accessibilityRole="button"
            accessibilityLabel={a.a11yLabel}
            accessibilityState={{ disabled: !!runningKind }}
            testID={`action-${a.kind}`}
            style={({ pressed }) => [
              styles.chip,
              pressed && styles.chipPressed,
              runningKind === a.kind && styles.chipRunning,
            ]}
          >
            <Ionicons name={a.icon as any} size={16} color={tokens.color.onSurface} />
            <Text style={styles.chipLabel} numberOfLines={1}>{a.label}</Text>
          </Pressable>
        ))}
      </ScrollView>
      {toast ? (
        <Animated.View
          entering={FadeIn.duration(120)}
          exiting={FadeOut.duration(160)}
          style={[styles.toast, toast.kind === 'error' && styles.toastError]}
          accessibilityLiveRegion="polite"
        >
          <Ionicons
            name={toast.kind === 'error' ? 'alert-circle-outline' : 'checkmark-circle-outline'}
            size={16}
            color={toast.kind === 'error' ? tokens.color.danger : tokens.color.success}
          />
          <Text style={styles.toastText}>{toast.text}</Text>
        </Animated.View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: tokens.color.surface,
    borderRadius: 16,
    padding: 12,
    borderWidth: 1,
    borderColor: tokens.color.border,
    gap: 10,
  },
  title: {
    fontSize: 11, fontWeight: '700', letterSpacing: 0.6,
    color: tokens.color.onSurfaceMuted, textTransform: 'uppercase',
  },
  row: { gap: 8, paddingRight: 8 },
  chip: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingVertical: 10, paddingHorizontal: 14,
    borderRadius: 999,
    minHeight: 44,
    borderWidth: 1,
    borderColor: tokens.color.border,
    backgroundColor: tokens.color.surfaceTertiary,
  },
  chipPressed: { opacity: 0.7, transform: [{ scale: 0.98 }] },
  chipRunning: { opacity: 0.55 },
  chipLabel: { color: tokens.color.onSurface, fontSize: 13, fontWeight: '600' },
  toast: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    borderRadius: 10, paddingVertical: 8, paddingHorizontal: 10,
    backgroundColor: tokens.color.surfaceTertiary,
    borderWidth: 1, borderColor: tokens.color.border,
  },
  toastError: {},
  toastText: { color: tokens.color.onSurface, fontSize: 13 },
});
