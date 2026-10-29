/**
 * Il punto del mattino: la giornata in una notifica, all'ora che scegli.
 * Appuntamenti, scadenze, promemoria e meteo di casa (anche se conviene
 * stendere). Scritto dal codice, senza modello: arriva anche quando
 * l'intelligenza artificiale non è disponibile.
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

export const BRIEF_HOURS = [6, 7, 8, 9, 10];

export function MorningBrief() {
  const { colors } = useTheme();
  const [state, setState] = useState<{ enabled: boolean; hour: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.morningBrief().then(setState).catch((e) => setError(humanizeError(e)));
  }, []);

  const save = async (body: { enabled?: boolean; hour?: number }) => {
    setError(null);
    try {
      setState(await api.setMorningBrief(body));
    } catch (e) {
      setError(humanizeError(e));
    }
  };

  return (
    <SettingCard testID="morning-brief">
      <View style={styles.header}>
        <View style={[styles.icon, { backgroundColor: colors.accentMuted }]}>
          <Ionicons name="sunny-outline" size={19} color={colors.accent} />
        </View>
        <View style={styles.headerText}>
          <Text style={[styles.title, { color: colors.textPrimary }]}>Il punto del mattino</Text>
          <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
            {state ? (state.enabled ? `Ogni giorno alle ${state.hour}:00` : 'Spento') : '…'}
          </Text>
        </View>
        <Switch value={!!state?.enabled} onValueChange={(v) => void save({ enabled: v })}
          disabled={!state} testID="morning-brief-switch" accessibilityLabel="Punto del mattino" />
      </View>
      <Text style={[styles.description, { color: colors.textSecondary }]}>
        Una notifica con gli appuntamenti e le scadenze del giorno, i promemoria e il meteo di casa,
        compreso se conviene stendere. Se non c'è niente da dire, non arriva.
      </Text>
      {state?.enabled ? (
        <View style={styles.buttons}>
          {BRIEF_HOURS.map((h) => (
            <ActionBtn key={h} primary={state.hour === h} label={`${h}:00`}
              onPress={() => void save({ hour: h })} testID={`morning-brief-hour-${h}`} />
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
