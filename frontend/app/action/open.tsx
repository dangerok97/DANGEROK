/**
 * Bridge route: opens Action Engine from Home deep-link `/action/open`.
 * Expects item payload via params or falls back after reading last focus — Home should call ActionEngine.open directly.
 */
import { useEffect, useState } from 'react';
import { View, Text, ActivityIndicator, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';

import { tokens } from '@/src/theme/tokens';
import { api } from '@/src/api/client';
import { ActionEngine } from '@/src/action-engine';
import { humanizeError } from '@/src/utils/errors';

export default function ActionOpenBridge() {
  const router = useRouter();
  const params = useLocalSearchParams<{
    item_id?: string;
    title?: string;
    type?: string;
    source_type?: string;
    source_id?: string;
  }>();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        let item = null as any;
        if (params.item_id || params.title) {
          item = {
            id: params.item_id || `bridge_${Date.now()}`,
            type: (params.type as any) || 'generic',
            title: params.title || 'Priorità',
            source_type: params.source_type || 'home',
            source_id: params.source_id || params.item_id || 'unknown',
            status: 'open',
            priority: 'today',
            urgency: 'none',
            actions: [],
            reason_factors: [],
          };
        } else {
          const home = await api.getHome();
          item = home.primary_focus;
        }
        if (!item) {
          setError('Nessuna priorità da aprire');
          return;
        }
        if (cancelled) return;
        await ActionEngine.open(item, router);
      } catch (e: any) {
        if (!cancelled) setError(humanizeError(e, 'default'));
      }
    })();
    return () => { cancelled = true; };
  }, [params.item_id, params.title, params.type, params.source_type, params.source_id, router]);

  return (
    <SafeAreaView style={styles.safe} testID="action-open-bridge">
      <View style={styles.box}>
        {error ? (
          <Text style={styles.error}>{error}</Text>
        ) : (
          <>
            <ActivityIndicator color={tokens.color.onSurface} />
            <Text style={styles.text}>Apro la guida ORA…</Text>
          </>
        )}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: tokens.color.surface, justifyContent: 'center' },
  box: { alignItems: 'center', gap: 12, padding: 24 },
  text: { color: tokens.color.onSurfaceMuted, fontSize: 14 },
  error: { color: tokens.color.error, fontSize: 14, textAlign: 'center' },
});
