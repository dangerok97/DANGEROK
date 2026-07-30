import { useCallback, useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import Animated, { FadeIn, FadeInDown } from 'react-native-reanimated';

import { tokens } from '@/src/theme/tokens';
import { api, GoogleCalendarResource } from '@/src/api/client';
import { humanizeError } from '@/src/utils/errors';
import { haptic } from '@/src/utils/haptic';
import { ActionBtn } from '@/src/components/ui/ActionBtn';

export default function ManageCalendars() {
  const { instance } = useLocalSearchParams<{ instance: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const [items, setItems] = useState<GoogleCalendarResource[] | null>(null);
  const [initialSelected, setInitialSelected] = useState<string[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    if (!instance) return;
    setError(null);
    try {
      const [cals, inst] = await Promise.all([
        api.googleCalendarCalendars(instance as string),
        api.googleCalendarInstances().then((r) => r.items.find((x) => x.id === instance) || null),
      ]);
      setItems(cals.items || []);
      const preset = inst?.selected_resource_ids || [];
      setInitialSelected(preset);
      setSelected(new Set(preset));
    } catch (e: any) {
      setError(humanizeError(e, 'calendars'));
    }
  }, [instance]);

  useEffect(() => { load(); }, [load]);

  const toggle = (id: string) => {
    haptic('select');
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const dirty =
    selected.size !== initialSelected.length ||
    [...selected].some((id) => !initialSelected.includes(id));

  const onSave = async () => {
    if (!instance) return;
    setSaving(true);
    setError(null);
    haptic('medium');
    try {
      const ids = [...selected];
      await api.googleCalendarSelectCalendars(instance as string, ids);
      haptic('success');
      setSaved(true);
      setInitialSelected(ids);
      setTimeout(() => router.back(), 700);
    } catch (e: any) {
      haptic('error');
      setError(humanizeError(e, 'select'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']} testID="manage-calendars">
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Pressable
          onPress={() => { haptic('tap'); router.back(); }}
          style={({ pressed }) => [styles.backBtn, pressed && styles.pressed]}
          accessibilityRole="button"
          accessibilityLabel="Torna indietro"
          hitSlop={12}
        >
          <Ionicons name="chevron-back" size={22} color={tokens.color.onSurface} />
        </Pressable>
        <Text style={styles.title}>Gestisci calendari</Text>
        <View style={{ width: 32 }} />
      </View>

      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ paddingHorizontal: 20, paddingBottom: insets.bottom + 120, gap: 12 }}
        showsVerticalScrollIndicator={false}
      >
        <Text style={styles.subtitle}>
          Scegli quali calendari ORA deve sincronizzare. Puoi cambiare in qualsiasi momento.
        </Text>

        {error ? (
          <Animated.View entering={FadeIn.duration(180)} style={styles.errorBanner} accessibilityRole="alert">
            <Ionicons name="alert-circle" size={16} color={tokens.color.error} />
            <Text style={styles.errorText}>{error}</Text>
          </Animated.View>
        ) : null}

        {items === null ? (
          <View style={{ paddingVertical: 40, alignItems: 'center' }}>
            <ActivityIndicator color={tokens.color.onSurfaceMuted} />
          </View>
        ) : items.length === 0 ? (
          <Text style={styles.muted}>Nessun calendario trovato.</Text>
        ) : (
          items.map((c, i) => {
            const on = selected.has(c.id);
            return (
              <Animated.View key={c.id} entering={FadeInDown.duration(220).delay(i * 40)}>
                <Pressable
                  onPress={() => toggle(c.id)}
                  style={({ pressed }) => [styles.row, on && styles.rowOn, pressed && styles.pressed]}
                  accessibilityRole="checkbox"
                  accessibilityState={{ checked: on }}
                  accessibilityLabel={`${c.summary}${c.primary ? ', principale' : ''}`}
                  testID={`cal-row-${i}`}
                >
                  <View style={[styles.checkbox, on && styles.checkboxOn]}>
                    {on ? <Ionicons name="checkmark" size={16} color={tokens.color.onBrand} /> : null}
                  </View>
                  <View style={{ flex: 1 }}>
                    <View style={styles.rowHead}>
                      <Text style={styles.rowTitle} numberOfLines={1}>{c.summary}</Text>
                      {c.primary ? (
                        <View style={styles.primaryPill}>
                          <Text style={styles.primaryPillText}>Principale</Text>
                        </View>
                      ) : null}
                    </View>
                    {c.access_role || c.time_zone ? (
                      <Text style={styles.rowMeta}>
                        {c.access_role === 'reader' ? 'Solo lettura' : c.access_role === 'owner' ? 'Il tuo' : c.access_role || ''}
                        {c.time_zone ? ` · ${c.time_zone}` : ''}
                      </Text>
                    ) : null}
                  </View>
                </Pressable>
              </Animated.View>
            );
          })
        )}

        {saved ? (
          <Animated.View entering={FadeIn.duration(200)} style={styles.savedBanner}>
            <Ionicons name="checkmark-circle" size={16} color={tokens.color.success} />
            <Text style={styles.savedText}>Salvato</Text>
          </Animated.View>
        ) : null}
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: Math.max(insets.bottom, 12) }]}>
        <ActionBtn
          primary
          icon="save-outline"
          label={saving ? 'Salvo…' : 'Salva selezione'}
          onPress={onSave}
          loading={saving}
          disabled={!dirty || selected.size === 0 || items === null}
          testID="btn-save-calendars"
        />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: tokens.color.surface },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 12, paddingVertical: 12,
  },
  backBtn: {
    width: 32, height: 32, borderRadius: 16,
    alignItems: 'center', justifyContent: 'center',
  },
  title: { fontSize: 17, fontWeight: '700', color: tokens.color.onSurface },
  subtitle: { fontSize: 13, color: tokens.color.onSurfaceMuted, lineHeight: 19, marginBottom: 4 },
  row: {
    flexDirection: 'row', gap: 12, alignItems: 'center',
    padding: 14,
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: tokens.radius.md,
    borderWidth: 1, borderColor: tokens.color.border,
    minHeight: tokens.touch.min,
  },
  rowOn: { borderColor: tokens.color.brand, backgroundColor: tokens.color.surfaceTertiary },
  checkbox: {
    width: 22, height: 22, borderRadius: 6,
    borderWidth: 1.5, borderColor: tokens.color.borderStrong,
    alignItems: 'center', justifyContent: 'center',
  },
  checkboxOn: { backgroundColor: tokens.color.brand, borderColor: tokens.color.brand },
  rowHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  rowTitle: { fontSize: 15, color: tokens.color.onSurface, fontWeight: '600', flexShrink: 1 },
  primaryPill: {
    backgroundColor: tokens.color.brand,
    paddingHorizontal: 6, paddingVertical: 2,
    borderRadius: tokens.radius.pill,
  },
  primaryPillText: { fontSize: 9, color: tokens.color.onBrand, fontWeight: '700', letterSpacing: 0.5 },
  rowMeta: { fontSize: 11, color: tokens.color.onSurfaceMuted, marginTop: 2 },
  muted: { fontSize: 13, color: tokens.color.onSurfaceMuted },
  errorBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: tokens.color.errorBg, borderColor: tokens.color.error, borderWidth: 1,
    padding: 12, borderRadius: tokens.radius.md,
  },
  errorText: { flex: 1, color: tokens.color.onSurface, fontSize: 13 },
  savedBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 4,
    backgroundColor: tokens.color.successBg, borderColor: tokens.color.success, borderWidth: 1,
    padding: 12, borderRadius: tokens.radius.md,
  },
  savedText: { color: tokens.color.success, fontSize: 13, fontWeight: '600' },
  footer: {
    padding: 16,
    borderTopWidth: 1, borderTopColor: tokens.color.border,
    backgroundColor: tokens.color.surface,
  },
  pressed: { opacity: 0.7 },
});
