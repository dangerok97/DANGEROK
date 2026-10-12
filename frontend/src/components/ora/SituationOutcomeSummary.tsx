import { useEffect, useReducer, useState, type ReactNode } from 'react';
import { AppState, Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import type { SituationOutcome } from '@/src/api/client';
import { ora, oraType } from '@/src/theme/oraSurface';
import { situationOutcomeView } from './situationOutcome';

export type SituationOutcomeColors = {
  text: string;
  secondary: string;
  attention: string;
};

const defaultColors: SituationOutcomeColors = {
  text: ora.ink, secondary: ora.ink2, attention: ora.attention,
};

/** The useful recommendation always precedes the machinery that checked it. */
export function SituationOutcomeSummary({
  outcome, desiredOutcome, situationRevision, followupStatus, readUnavailable,
  colors = defaultColors, compact = false, testID = 'situation-outcome',
}: {
  outcome?: SituationOutcome | null;
  desiredOutcome?: string | null;
  situationRevision?: number;
  followupStatus?: string | null;
  readUnavailable?: boolean;
  colors?: SituationOutcomeColors;
  compact?: boolean;
  testID?: string;
}) {
  const [, refreshClock] = useReducer((version: number) => version + 1, 0);
  useEffect(() => {
    const deadline = Date.parse(outcome?.valid_until || '');
    const remaining = deadline - Date.now();
    const timer = Number.isFinite(remaining) && remaining > 0
      ? setTimeout(refreshClock, Math.min(remaining + 1, 2147483647)) : null;
    const appState = AppState.addEventListener('change', state => {
      if (state === 'active') refreshClock();
    });
    return () => { if (timer !== null) clearTimeout(timer); appState.remove(); };
  }, [outcome?.valid_until]);

  const view = situationOutcomeView({ outcome, desiredOutcome, situationRevision, followupStatus, readUnavailable });
  return (
    <View style={styles.summary} testID={testID} accessibilityLiveRegion="polite">
      <Text style={[oraType.small, { color: view.needsAttention ? colors.attention : colors.secondary }]}>
        {view.label}
      </Text>
      <Text style={[compact ? oraType.section : oraType.title, { color: colors.text }]}
        testID={`${testID}-headline`}>
        {view.headline}
      </Text>
      {view.window ? <Text style={[oraType.body, { color: colors.text, fontWeight: '600' }]}
        testID={`${testID}-window`}>
        Finestra stimata: {view.window}
      </Text> : null}
      {view.detail ? <Text style={[oraType.body, { color: colors.secondary }]}>{view.detail}</Text> : null}
      {view.basis ? <Text style={[oraType.small, { color: colors.secondary }]}>{view.basis}</Text> : null}
    </View>
  );
}

/** Scheduler, sources and prior state remain available without leading the card. */
export function SituationDetails({
  children, colors = defaultColors, testID = 'situation-details',
}: { children: ReactNode; colors?: SituationOutcomeColors; testID?: string }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <View style={styles.details} testID={testID}>
      <Pressable accessibilityRole="button" accessibilityState={{ expanded }}
        aria-expanded={expanded}
        accessibilityLabel="Dettagli del controllo" onPress={() => setExpanded(value => !value)}
        style={styles.toggle} testID={`${testID}-toggle`}>
        <Text style={[oraType.small, { color: colors.secondary, fontWeight: '600', flex: 1 }]}>
          Dettagli del controllo
        </Text>
        <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={16} color={colors.secondary} />
      </Pressable>
      {expanded ? <View style={styles.detailsBody}>{children}</View> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  summary: { gap: 6 },
  details: { gap: 4 },
  toggle: { minHeight: 44, flexDirection: 'row', alignItems: 'center', gap: 8 },
  detailsBody: { gap: 12 },
});
