import { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Pressable,
  ActivityIndicator,
  RefreshControl,
  Modal,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import Animated, { FadeInDown, FadeIn } from 'react-native-reanimated';
import * as Haptics from 'expo-haptics';
import { Ionicons } from '@expo/vector-icons';

import { tokens } from '@/src/theme/tokens';
import { api, ApiTask } from '@/src/api/client';

const kindIcon: Record<string, keyof typeof Ionicons.glyphMap> = {
  travel: 'navigate-outline',
  bill: 'flash-outline',
  message: 'chatbubble-outline',
  health: 'moon-outline',
  finance: 'trending-up-outline',
  generic: 'ellipse-outline',
};

export default function HomeScreen() {
  const insets = useSafeAreaInsets();
  const [tasks, setTasks] = useState<ApiTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [resolveOpen, setResolveOpen] = useState(false);
  const [resolveTask, setResolveTask] = useState<ApiTask | null>(null);
  const [resolveText, setResolveText] = useState<string>('');
  const [resolveLoading, setResolveLoading] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api.priorities();
      setTasks(r.items);
    } catch (e) {
      // ignore, keep UI calm
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const onRefresh = () => {
    setRefreshing(true);
    load();
  };

  const openResolve = async (t: ApiTask) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    setResolveTask(t);
    setResolveText('');
    setResolveOpen(true);
    setResolveLoading(true);
    try {
      const r = await api.resolveTask(t.id);
      setResolveText(r.solution);
    } catch (e: any) {
      setResolveText('ORA non è riuscita a proporre una soluzione ora. Riprova tra poco.');
    } finally {
      setResolveLoading(false);
    }
  };

  const dismissTask = async (t: ApiTask) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setTasks((prev) => prev.filter((x) => x.id !== t.id));
    try { await api.dismissTask(t.id); } catch {}
  };

  const completeFromModal = async () => {
    if (!resolveTask) return;
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    try { await api.completeTask(resolveTask.id); } catch {}
    setTasks((prev) => prev.filter((x) => x.id !== resolveTask.id));
    setResolveOpen(false);
  };

  return (
    <SafeAreaView edges={['top']} style={styles.root}>
      <ScrollView
        contentContainerStyle={[styles.scroll, { paddingBottom: 96 + insets.bottom }]}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={tokens.color.onSurfaceMuted} />
        }
      >
        <View style={styles.header}>
          <Text style={styles.brand} testID="home-brand-title">ORA</Text>
          <Text style={styles.h1}>Cosa conta{'\n'}adesso</Text>
        </View>

        {loading ? (
          <View style={styles.empty}>
            <ActivityIndicator color={tokens.color.onSurfaceMuted} />
          </View>
        ) : tasks.length === 0 ? (
          <Animated.View entering={FadeIn.duration(400)} style={styles.empty} testID="home-empty-state">
            <Ionicons name="checkmark-circle-outline" size={40} color={tokens.color.onSurfaceMuted} />
            <Text style={styles.emptyTitle}>Tutto risolto.</Text>
            <Text style={styles.emptySub}>Goditi il momento.</Text>
          </Animated.View>
        ) : (
          <View style={styles.cards}>
            {tasks.map((t, i) => (
              <Animated.View
                key={t.id}
                entering={FadeInDown.duration(380).delay(i * 60)}
                style={styles.card}
                testID={`priority-card-${i}`}
              >
                <View style={styles.cardHeaderRow}>
                  <View style={styles.metaRow}>
                    <Ionicons
                      name={kindIcon[t.kind || 'generic'] || 'ellipse-outline'}
                      size={14}
                      color={tokens.color.onSurfaceMuted}
                    />
                    <Text style={styles.metaLabel}>{(t.kind || 'nota').toUpperCase()}</Text>
                  </View>
                  <Pressable
                    testID={`priority-dismiss-${i}`}
                    onPress={() => dismissTask(t)}
                    hitSlop={12}
                  >
                    <Ionicons name="close" size={18} color={tokens.color.onSurfaceDim} />
                  </Pressable>
                </View>

                <Text style={styles.cardTitle}>{t.title}</Text>
                {t.context ? <Text style={styles.cardContext}>{t.context}</Text> : null}

                <Pressable
                  testID={`priority-resolve-${i}`}
                  onPress={() => openResolve(t)}
                  style={({ pressed }) => [styles.resolveBtn, pressed && styles.resolveBtnPressed]}
                >
                  <Text style={styles.resolveText}>RISOLVI</Text>
                  <Ionicons name="arrow-forward" size={18} color={tokens.color.onBrand} />
                </Pressable>
              </Animated.View>
            ))}
          </View>
        )}
      </ScrollView>

      {/* Resolve Modal */}
      <Modal
        visible={resolveOpen}
        animationType="slide"
        transparent
        onRequestClose={() => setResolveOpen(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalSheet} testID="resolve-modal">
            <View style={styles.grabber} />
            <Text style={styles.modalKicker}>SOLUZIONE PROPOSTA</Text>
            <Text style={styles.modalTitle}>{resolveTask?.title}</Text>

            <ScrollView style={styles.modalScroll} showsVerticalScrollIndicator={false}>
              {resolveLoading ? (
                <View style={{ paddingVertical: tokens.spacing.xxl }}>
                  <ActivityIndicator color={tokens.color.onSurfaceMuted} />
                  <Text style={styles.modalBusy}>ORA sta pensando…</Text>
                </View>
              ) : (
                <Text style={styles.modalBody} testID="resolve-solution-text">{resolveText}</Text>
              )}
            </ScrollView>

            <View style={styles.modalActions}>
              <Pressable
                testID="resolve-close-button"
                onPress={() => setResolveOpen(false)}
                style={({ pressed }) => [styles.secondaryBtn, pressed && styles.pressed]}
              >
                <Text style={styles.secondaryText}>Più tardi</Text>
              </Pressable>
              <Pressable
                testID="resolve-done-button"
                onPress={completeFromModal}
                style={({ pressed }) => [styles.primaryBtn, pressed && styles.pressed]}
              >
                <Text style={styles.primaryText}>Fatto</Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: tokens.color.surface },
  scroll: { paddingHorizontal: tokens.spacing.lg, paddingTop: tokens.spacing.sm },
  header: { paddingHorizontal: tokens.spacing.xs, marginBottom: tokens.spacing.xl, gap: tokens.spacing.xs },
  brand: { color: tokens.color.onSurfaceMuted, fontSize: tokens.fs.sm, fontWeight: '700', letterSpacing: 2 },
  h1: { color: tokens.color.onSurface, fontSize: tokens.fs.xxxl, fontWeight: '700', lineHeight: 38, letterSpacing: -0.8 },
  empty: { paddingVertical: 80, alignItems: 'center', gap: 6 },
  emptyTitle: { color: tokens.color.onSurface, fontSize: tokens.fs.xl, fontWeight: '600' },
  emptySub: { color: tokens.color.onSurfaceMuted, fontSize: tokens.fs.lg },
  cards: { gap: tokens.spacing.md },
  card: {
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: tokens.color.border,
    padding: tokens.spacing.lg,
    gap: tokens.spacing.md,
  },
  cardHeaderRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  metaLabel: {
    color: tokens.color.onSurfaceMuted,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 1.4,
  },
  cardTitle: {
    color: tokens.color.onSurface,
    fontSize: tokens.fs.xl,
    fontWeight: '600',
    lineHeight: 26,
    letterSpacing: -0.3,
  },
  cardContext: {
    color: tokens.color.onSurfaceMuted,
    fontSize: tokens.fs.base,
    lineHeight: 20,
  },
  resolveBtn: {
    marginTop: tokens.spacing.xs,
    height: 56,
    borderRadius: tokens.radius.md,
    backgroundColor: tokens.color.brand,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: tokens.spacing.sm,
  },
  resolveBtnPressed: { transform: [{ scale: 0.98 }], opacity: 0.9 },
  resolveText: {
    color: tokens.color.onBrand,
    fontSize: tokens.fs.lg,
    fontWeight: '700',
    letterSpacing: 1.5,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.6)',
    justifyContent: 'flex-end',
  },
  modalSheet: {
    backgroundColor: tokens.color.surfaceSecondary,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    padding: tokens.spacing.xl,
    paddingBottom: tokens.spacing.xxl,
    maxHeight: '85%',
  },
  grabber: {
    alignSelf: 'center',
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: tokens.color.borderStrong,
    marginBottom: tokens.spacing.lg,
  },
  modalKicker: {
    color: tokens.color.onSurfaceMuted,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 1.6,
    marginBottom: tokens.spacing.sm,
  },
  modalTitle: {
    color: tokens.color.onSurface,
    fontSize: tokens.fs.xxl,
    fontWeight: '700',
    letterSpacing: -0.4,
    marginBottom: tokens.spacing.lg,
  },
  modalScroll: { maxHeight: 420 },
  modalBody: {
    color: tokens.color.onSurface,
    fontSize: tokens.fs.lg,
    lineHeight: 26,
  },
  modalBusy: {
    color: tokens.color.onSurfaceMuted,
    textAlign: 'center',
    marginTop: tokens.spacing.md,
    fontSize: tokens.fs.base,
  },
  modalActions: {
    flexDirection: 'row',
    gap: tokens.spacing.md,
    marginTop: tokens.spacing.xl,
  },
  secondaryBtn: {
    flex: 1,
    height: 52,
    borderRadius: tokens.radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: tokens.color.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  secondaryText: { color: tokens.color.onSurface, fontSize: tokens.fs.lg, fontWeight: '500' },
  primaryBtn: {
    flex: 1,
    height: 52,
    borderRadius: tokens.radius.md,
    backgroundColor: tokens.color.brand,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryText: { color: tokens.color.onBrand, fontSize: tokens.fs.lg, fontWeight: '700' },
  pressed: { opacity: 0.7 },
});
