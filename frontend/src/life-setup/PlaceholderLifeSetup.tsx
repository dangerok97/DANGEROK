/**
 * Sprint 1 — temporary Life Setup placeholder (pre-Home gate).
 * Replaced later by the conversational Life Experience without changing the gate.
 */
import { useState } from 'react';
import { View, Text, StyleSheet, Pressable, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { tokens } from '@/src/theme/tokens';
import { useAuth } from '@/src/contexts/AuthContext';
import { completeLifeSetupGate, routeByLifeSetupGate } from '@/src/life-setup/gate';

/** Rollback-only UI — not mounted on the normal /life-setup path (Sprint 2B). */
export function PlaceholderLifeSetup() {
  const router = useRouter();
  const { user } = useAuth();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const onComplete = async () => {
    if (!user?.user_id || busy) return;
    setBusy(true);
    setErr(null);
    try {
      await completeLifeSetupGate(user.user_id);
      await routeByLifeSetupGate(router, user.user_id);
    } catch {
      setErr('Non sono riuscito a salvare il completamento. Riprova.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <SafeAreaView style={styles.root} edges={['top', 'bottom']} testID="life-setup-placeholder">
      <View style={styles.body}>
        <Text style={styles.title} accessibilityRole="header" testID="life-setup-title">
          Life Setup
        </Text>
        <Text style={styles.copy} testID="life-setup-copy">
          Placeholder temporaneo della Life Setup Experience.
        </Text>
        {err ? (
          <Text style={styles.err} accessibilityLiveRegion="polite">
            {err}
          </Text>
        ) : null}
      </View>
      <Pressable
        style={({ pressed }) => [
          styles.cta,
          { opacity: busy ? 0.55 : pressed ? 0.85 : 1 },
        ]}
        onPress={onComplete}
        disabled={busy}
        accessibilityRole="button"
        accessibilityLabel="Completa Setup"
        accessibilityState={{ busy, disabled: busy }}
        testID="life-setup-complete"
      >
        {busy ? (
          <ActivityIndicator color={tokens.color.onBrand} />
        ) : (
          <Text style={styles.ctaText}>Completa Setup</Text>
        )}
      </Pressable>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: tokens.color.surface,
    paddingHorizontal: tokens.spacing.xl,
    paddingBottom: tokens.spacing.xl,
    justifyContent: 'space-between',
  },
  body: {
    flex: 1,
    justifyContent: 'center',
    gap: tokens.spacing.md,
  },
  title: {
    fontSize: tokens.fs.xxxl,
    fontWeight: '700',
    color: tokens.color.onSurface,
    letterSpacing: -0.5,
  },
  copy: {
    fontSize: tokens.fs.lg,
    lineHeight: 24,
    color: tokens.color.onSurfaceMuted,
  },
  err: {
    fontSize: tokens.fs.base,
    color: tokens.color.error,
  },
  cta: {
    minHeight: tokens.touch.min,
    borderRadius: tokens.radius.md,
    backgroundColor: tokens.color.brand,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 14,
  },
  ctaText: {
    fontSize: tokens.fs.lg,
    fontWeight: '600',
    color: tokens.color.onBrand,
  },
});
