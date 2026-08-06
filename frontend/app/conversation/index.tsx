/**
 * Conversation Engine entry route — bridges to Action Engine one-question UI.
 * Query: ?text=... | ?resume=sessionId — never opens a chat thread.
 */
import { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { tokens } from '@/src/theme/tokens';
import { ConversationEngine } from '@/src/conversation-engine';
import { humanizeError } from '@/src/utils/errors';

export default function ConversationEntryScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ text?: string; resume?: string; origin?: string }>();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        if (params.resume) {
          await ConversationEngine.resume(router, { session_id: String(params.resume) });
          return;
        }
        const text = (params.text || '').trim();
        if (!text) {
          // Empty entry → back to Home PARLA
          router.replace('/(tabs)' as any);
          return;
        }
        await ConversationEngine.start(text, router, {
          origin: (params.origin as any) || 'text',
        });
      } catch (e: any) {
        if (!cancelled) setError(humanizeError(e, 'default'));
      }
    })();
    return () => { cancelled = true; };
  }, [params.text, params.resume, params.origin, router]);

  return (
    <SafeAreaView style={styles.root} testID="conversation-entry">
      <View style={styles.center}>
        {error ? (
          <Text style={styles.err}>{error}</Text>
        ) : (
          <>
            <ActivityIndicator color={tokens.color.onSurface} />
            <Text style={styles.msg}>ORA sta preparando il prossimo passo…</Text>
          </>
        )}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: tokens.color.surface },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12, padding: 24 },
  msg: { color: tokens.color.onSurfaceMuted, fontSize: 14 },
  err: { color: tokens.color.error, fontSize: 14, textAlign: 'center' },
});
