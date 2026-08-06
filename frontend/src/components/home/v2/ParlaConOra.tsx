/**
 * Home entry — PARLA CON ORA.
 * Mic (voice-ready stub) + text + send → ConversationEngine.start.
 * NOT a chat composer for infinite threads.
 */
import { useState } from 'react';
import {
  View, Text, TextInput, Pressable, StyleSheet, ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { tokens } from '@/src/theme/tokens';
import { ConversationEngine } from '@/src/conversation-engine';
import { haptic } from '@/src/utils/haptic';
import { humanizeError } from '@/src/utils/errors';

type Props = {
  onError?: (msg: string) => void;
};

export function ParlaConOra({ onError }: Props) {
  const router = useRouter();
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [voiceHint, setVoiceHint] = useState<string | null>(null);

  const submit = async (origin: 'home' | 'voice' = 'home') => {
    const t = text.trim();
    if (!t || busy) return;
    setBusy(true);
    setVoiceHint(null);
    try {
      haptic('tap');
      if (origin === 'voice') {
        await ConversationEngine.startFromVoiceStub(t, router);
      } else {
        await ConversationEngine.start(t, router, { origin: 'home' });
      }
      setText('');
    } catch (e: any) {
      haptic('error');
      onError?.(humanizeError(e, 'default'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.wrap} testID="parla-con-ora">
      <Text style={styles.h} accessibilityRole="header">PARLA CON ORA</Text>
      <Text style={styles.sub}>Scrivi o parla — ORA organizza con te. Non è una chat.</Text>
      <View style={styles.row}>
        <Pressable
          testID="parla-mic"
          accessibilityLabel="Voce (riconoscimento non ancora attivo — usa il testo)"
          style={({ pressed }) => [styles.mic, pressed && { opacity: 0.7 }]}
          onPress={() => {
            haptic('select');
            setVoiceHint(
              'Voce pronta nella struttura: per ora digita il testo — stesso motore, niente STT.',
            );
            // Same engine path when text present
            if (text.trim()) submit('voice');
          }}
          disabled={busy}
        >
          <Ionicons name="mic-outline" size={22} color={tokens.color.onSurface} />
        </Pressable>
        <TextInput
          testID="parla-input"
          value={text}
          onChangeText={setText}
          placeholder="Es. Fra due settimane parto."
          placeholderTextColor={tokens.color.onSurfaceMuted}
          style={styles.input}
          editable={!busy}
          returnKeyType="send"
          onSubmitEditing={() => submit('home')}
          keyboardAppearance="dark"
        />
        <Pressable
          testID="parla-send"
          accessibilityLabel="Invia a ORA"
          style={({ pressed }) => [
            styles.send,
            (!text.trim() || busy) && styles.sendDisabled,
            pressed && { opacity: 0.8 },
          ]}
          onPress={() => submit('home')}
          disabled={busy || !text.trim()}
        >
          {busy ? (
            <ActivityIndicator color={tokens.color.onBrand} size="small" />
          ) : (
            <Ionicons name="arrow-forward" size={20} color={tokens.color.onBrand} />
          )}
        </Pressable>
      </View>
      {voiceHint ? (
        <Text style={styles.hint} testID="parla-voice-stub-hint">{voiceHint}</Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: 8,
    marginBottom: tokens.spacing.xs,
  },
  h: {
    fontSize: 13,
    fontWeight: '700',
    letterSpacing: 1.2,
    color: tokens.color.onSurfaceDim,
  },
  sub: {
    fontSize: 12,
    color: tokens.color.onSurfaceMuted,
    lineHeight: 16,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: tokens.radius.lg,
    borderWidth: 1,
    borderColor: tokens.color.border,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  mic: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: tokens.color.surface,
  },
  input: {
    flex: 1,
    minHeight: 40,
    color: tokens.color.onSurface,
    fontSize: 15,
    paddingVertical: 8,
  },
  send: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: tokens.color.brand,
  },
  sendDisabled: { opacity: 0.4 },
  hint: {
    fontSize: 11,
    color: tokens.color.onSurfaceDim,
    lineHeight: 14,
  },
});
