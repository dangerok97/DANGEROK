/**
 * DEV / diagnostic only — AI Core harness entry.
 * Production surfaces must use /ora. Do not link from Home / Ambient / Workspace.
 */
import { useCallback, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { api } from '@/src/api/client';
import { OraComposer } from '@/src/components/ora/OraComposer';
import { FocusScreen, FOCUS_DECISION_MAX_WIDTH } from '@/src/shell';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { humanizeError } from '@/src/utils/errors';

/** @internal DEV harness — not a production destination */
export default function OraAiDevStart() {
  const router = useRouter();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = useCallback(async () => {
    const msg = text.trim();
    if (!msg || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.aiCoreStart({
        text: msg,
        origin: 'text',
        entry_point: 'ora',
      });
      const id = res.session_id;
      if (!id) throw new Error('Nessuna sessione');
      // Stay on DEV route for diagnostics
      router.replace(`/ora-ai/${id}` as any);
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
      setBusy(false);
    }
  }, [text, busy, router]);

  return (
    <FocusScreen>
      <View
        style={[
          styles.wrap,
          { maxWidth: FOCUS_DECISION_MAX_WIDTH, paddingBottom: insets.bottom + 16 },
        ]}
      >
        <Text style={[styles.dev, { color: colors.textTertiary }]} testID="ora-ai-dev-label">
          DEV / diagnostica — produzione: /ora
        </Text>
        <Text style={[styles.hint, { color: colors.textSecondary }]}>
          Prototipo AI-native. Stesso runtime di /ora.
        </Text>
        {error ? <Text style={{ color: colors.error }}>{error}</Text> : null}
        <OraComposer
          value={text}
          onChangeText={setText}
          onSend={() => void start()}
          busy={busy}
          placeholder="Cosa vuoi fare?"
          showMicStub={false}
          testID="ora-ai-start"
        />
      </View>
    </FocusScreen>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, width: '100%', alignSelf: 'center', paddingHorizontal: tokens.spacing.md, gap: 12 },
  dev: { fontSize: 12, marginTop: 8, letterSpacing: 0.4 },
  hint: { fontSize: 15, lineHeight: 22 },
});
