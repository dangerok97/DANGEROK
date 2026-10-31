/**
 * La sera prima: cosa c'è domani, quando partire, se serve l'ombrello.
 * Solo quando domani c'è qualcosa. Scritto dal codice, senza modello.
 */
import { useEffect, useState } from 'react';
import { StyleSheet, Switch, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { api } from '@/src/api/client';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { ActionBtn } from '@/src/components/ui/ActionBtn';
import { SettingCard } from '@/src/components/account';
import { humanizeError } from '@/src/utils/errors';

export const EVENING_HOURS = [18, 19, 20, 21, 22];
/** 20 vuol dire 20:30, l'ora predefinita; le altre sono ore piene. */
export const orarioSera = (h: number) => (h === 20 ? '20:30' : `${h}:00`);

export function EveningBrief() {
  const { colors } = useTheme();
  const [state, setState] = useState<{ enabled: boolean; hour: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.eveningBrief().then(setState).catch((e) => setError(humanizeError(e)));
  }, []);

  const save = async (body: { enabled?: boolean; hour?: number }) => {
    setError(null);
    try {
      setState(await api.setEveningBrief(body));
    } catch (e) {
      setError(humanizeError(e));
    }
  };

  return (
    <SettingCard testID="evening-brief">
      <View style={styles.header}>
        <View style={[styles.icon, { backgroundColor: colors.accentMuted }]}>
          <Ionicons name="moon-outline" size={19} color={colors.accent} />
        </View>
        <View style={styles.headerText}>
          <Text style={[styles.title, { color: colors.textPrimary }]}>La sera prima</Text>
          <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
            {state ? (state.enabled ? `Alle ${orarioSera(state.hour)}, se domani c'è qualcosa` : 'Spento') : '…'}
          </Text>
        </View>
        <Switch value={!!state?.enabled} onValueChange={(v) => void save({ enabled: v })}
          disabled={!state} testID="evening-brief-switch" accessibilityLabel="Avviso della sera prima" />
      </View>
      <Text style={[styles.description, { color: colors.textSecondary }]}>
        La sera, gli appuntamenti e le scadenze di domani, a che ora partire e se servirà l'ombrello.
        Se domani non c'è niente, non arriva.
      </Text>
      {state?.enabled ? (
        <View style={styles.buttons}>
          {EVENING_HOURS.map((h) => (
            <ActionBtn key={h} primary={state.hour === h} label={orarioSera(h)}
              onPress={() => void save({ hour: h })} testID={`evening-brief-hour-${h}`} />
          ))}
        </View>
      ) : null}
      {error ? <Text accessibilityRole="alert" style={[styles.description, { color: colors.error }]}>{error}</Text> : null}
    </SettingCard>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.md },
  icon: { width: 40, height: 40, borderRadius: tokens.radius.sm, alignItems: 'center', justifyContent: 'center' },
  headerText: { flex: 1, minWidth: 0, gap: 2 },
  title: { fontSize: 16, fontWeight: '650' as any },
  subtitle: { fontSize: 12, lineHeight: 17 },
  description: { fontSize: 13, lineHeight: 19, marginTop: 6 },
  buttons: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 },
});
