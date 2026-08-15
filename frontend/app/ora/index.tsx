/**
 * Production ORA — new conversational thread (AI Core) with real attachments.
 */
import { useCallback, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { api } from '@/src/api/client';
import {
  OraComposer,
  PendingAttachment,
  pickOraAttachment,
} from '@/src/components/ora/OraComposer';
import { FocusScreen, FOCUS_DECISION_MAX_WIDTH } from '@/src/shell';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { humanizeError } from '@/src/utils/errors';
import { buildOraConversationHref } from '@/src/ora/oraNav';

export default function OraProductionStart() {
  const router = useRouter();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);

  const onAttach = useCallback(async () => {
    setError(null);
    try {
      const picked = await pickOraAttachment();
      if (!picked) return;
      const localId = `loc_${Date.now()}`;
      setAttachments((prev) => [
        ...prev,
        { localId, name: picked.name, mimeType: picked.type, status: 'uploading' },
      ]);
      try {
        const res = await api.aiCoreFileUpload(picked, null);
        if (!res.ok || !res.file_id) throw new Error(res.message || 'Upload fallito');
        setAttachments((prev) =>
          prev.map((a) =>
            a.localId === localId
              ? {
                  ...a,
                  fileId: res.file_id,
                  documentId: res.document_id,
                  status: 'ready',
                  textAvailable: Boolean(res.text_available),
                }
              : a,
          ),
        );
      } catch (e: any) {
        setAttachments((prev) =>
          prev.map((a) =>
            a.localId === localId
              ? { ...a, status: 'failed', error: humanizeError(e, 'default') }
              : a,
          ),
        );
      }
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
    }
  }, []);

  const send = useCallback(async () => {
    const msg = text.trim();
    const ready = attachments.filter((a) => a.status === 'ready' && a.fileId);
    if ((!msg && !ready.length) || busy) return;
    if (attachments.some((a) => a.status === 'uploading')) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.aiCoreStart({
        text: msg || `[Allegato: ${ready.map((a) => a.name).join(', ')}]`,
        origin: 'text',
        entry_point: 'ora',
        attachments: ready.map((a) => ({
          file_id: a.fileId!,
          document_id: a.documentId,
          display_name: a.name,
          mime_type: a.mimeType,
        })),
      } as any);
      const id = res.session_id;
      if (!id) throw new Error('Nessuna sessione');
      setText('');
      setAttachments([]);
      router.replace(
        buildOraConversationHref({ sessionId: id, entryPoint: 'ora' }) as any,
      );
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
      setBusy(false);
    }
  }, [text, attachments, busy, router]);

  return (
    <FocusScreen testID="ora-production-start">
      <View
        style={[
          styles.wrap,
          { maxWidth: FOCUS_DECISION_MAX_WIDTH, paddingBottom: insets.bottom + 16 },
        ]}
      >
        <Text style={[styles.hint, { color: colors.textSecondary }]}>
          Una sola ORA. Puoi scrivere e allegare file come contesto.
        </Text>
        {error ? <Text style={{ color: colors.error }}>{error}</Text> : null}
        {hint ? <Text style={[styles.hint, { color: colors.textTertiary }]}>{hint}</Text> : null}
        <OraComposer
          value={text}
          onChangeText={setText}
          onSend={() => void send()}
          busy={busy}
          placeholder="Cosa vuoi raccontare a ORA…"
          showAttach
          attachments={attachments}
          onAttachPress={() => void onAttach()}
          onRemoveAttachment={(id) =>
            setAttachments((prev) => prev.filter((a) => a.localId !== id))
          }
          onMicPress={() =>
            setHint('Voce: digita per ora — stesso motore, niente riconoscimento vocale.')
          }
          testID="ora-start-composer"
        />
      </View>
    </FocusScreen>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flex: 1,
    width: '100%',
    alignSelf: 'center',
    paddingHorizontal: tokens.spacing.md,
    gap: 12,
    justifyContent: 'flex-end',
  },
  hint: { fontSize: 15, lineHeight: 22, marginTop: 8 },
});
