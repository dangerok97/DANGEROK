import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { tokens } from '@/src/theme/tokens';
import type { LLMProviderId, LLMProviderInfo, LLMProvidersStatus } from '@/src/api/client';

/**
 * Developer diagnostics — which model answered, what the failover chain is,
 * what is reachable right now.
 *
 * This is genuinely useful and is not being deleted; it is being moved out of
 * the consumer product. A person using ORA has no way to act on "Gemini →
 * OpenAI → Ollama → Emergent, fallback automatico su errori": it asks them to
 * hold a mental model of an inference stack in order to use a life assistant,
 * and it quietly makes the product's own reliability the user's problem. Which
 * model wrote a sentence is an implementation state; the human state is
 * whether ORA answered well.
 *
 * `__DEV__` is false in any production bundle, so this renders nowhere the user
 * can reach — the block is not merely hidden by styling, it is not built.
 */

type Props = {
  llmStatus: LLMProvidersStatus | null;
  busy: string | null;
  onSelectProvider: (id: LLMProviderId) => void;
};

const PROVIDER_IDS: LLMProviderId[] = ['gemini', 'openai', 'ollama', 'emergent'];

export function DevDiagnostics({ llmStatus, busy, onSelectProvider }: Props) {
  if (!__DEV__) return null;

  return (
    <>
      <Text style={styles.sectionLabel}>Diagnostica · solo sviluppo</Text>
      <View style={styles.card} testID="dev-diagnostics">
        <Text style={styles.devBadge}>Non visibile in produzione</Text>
        <Text style={styles.aiActive}>
          Attivo:{' '}
          <Text style={styles.aiActiveValue}>
            {llmStatus?.active ? llmStatus.active : 'nessuno (parsing locale)'}
          </Text>
        </Text>
        <Text style={styles.aiHint}>
          Priorità: Gemini → OpenAI → Ollama → Emergent. Fallback automatico su errori.
        </Text>
        {PROVIDER_IDS.map((id) => {
          const info = llmStatus?.providers?.find((p: LLMProviderInfo) => p.id === id);
          const selected =
            (llmStatus?.user_preference || llmStatus?.preferred || 'auto') === id ||
            (!llmStatus?.user_preference && !llmStatus?.preferred && llmStatus?.active === id);
          const available = !!info?.available;
          const configured = !!info?.configured;
          return (
            <Pressable
              key={id}
              testID={`ai-provider-${id}`}
              onPress={() => onSelectProvider(id)}
              style={({ pressed }) => [styles.aiRow, pressed && styles.pressed]}
              accessibilityRole="radio"
              accessibilityState={{ selected }}
            >
              <View style={[styles.radio, selected && styles.radioOn]} />
              <View style={{ flex: 1 }}>
                <Text style={styles.aiLabel}>{info?.label || id}</Text>
                <Text style={styles.aiMeta}>
                  {!configured && !available
                    ? 'Non configurato'
                    : available
                      ? `Disponibile${info?.model ? ` · ${info.model}` : ''}`
                      : 'Configurato ma non disponibile'}
                </Text>
              </View>
              {busy === `llm_${id}` ? <ActivityIndicator color={tokens.color.onSurface} /> : null}
            </Pressable>
          );
        })}
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  sectionLabel: {
    color: tokens.color.onSurfaceMuted,
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 1.4,
    textTransform: 'uppercase',
    marginTop: tokens.spacing.sm,
  },
  card: {
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: tokens.color.border,
    padding: tokens.spacing.lg,
    gap: tokens.spacing.sm,
  },
  devBadge: {
    color: tokens.color.warning,
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.6,
  },
  aiActive: { color: tokens.color.onSurface, fontSize: 14 },
  aiActiveValue: { fontWeight: '700' },
  aiHint: { color: tokens.color.onSurfaceMuted, fontSize: 12, lineHeight: 18 },
  aiRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: tokens.spacing.md,
    paddingVertical: tokens.spacing.sm,
    minHeight: tokens.touch.min,
  },
  radio: {
    width: 18,
    height: 18,
    borderRadius: 9,
    borderWidth: 2,
    borderColor: tokens.color.border,
  },
  radioOn: {
    borderColor: tokens.color.accent,
    backgroundColor: tokens.color.accent,
  },
  aiLabel: { color: tokens.color.onSurface, fontSize: 14, fontWeight: '600' },
  aiMeta: { color: tokens.color.onSurfaceMuted, fontSize: 12, marginTop: 2 },
  pressed: { opacity: 0.6 },
});
