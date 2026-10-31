/**
 * Il controllo automatico: ogni mattina ORA prova da sola promemoria, meteo,
 * percorsi, avviso di partenza e punto del mattino. Qui si vede com'è andata,
 * senza aspettare che qualcosa si rompa sotto gli occhi di chi la usa.
 */
import { useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { api } from '@/src/api/client';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { SettingCard } from '@/src/components/account';

type Run = Awaited<ReturnType<typeof api.oraCheck>>['runs'][number];

export function riassuntoControllo(runs: Run[]): string {
  const last = runs[0];
  if (!last) return 'Il primo controllo arriva domattina.';
  const giorno = last.day.split('-').reverse().slice(0, 2).join('/');
  if (last.ok) return `Ultimo controllo (${giorno}): tutto funziona.`;
  const ko = last.checks.filter(c => !c.ok).map(c => c.text);
  return `Ultimo controllo (${giorno}): ${ko.join('; ')}.`;
}

export function OraCheck() {
  const { colors } = useTheme();
  const [runs, setRuns] = useState<Run[] | null>(null);
  useEffect(() => { api.oraCheck().then(r => setRuns(r.runs)).catch(() => setRuns([])); }, []);
  const ok = !!runs?.[0]?.ok;
  return (
    <SettingCard testID="ora-check">
      <View style={styles.header}>
        <View style={[styles.icon, { backgroundColor: colors.accentMuted }]}>
          <Ionicons name={runs && runs[0] && !ok ? 'alert-circle-outline' : 'pulse-outline'} size={19}
            color={runs && runs[0] && !ok ? colors.error : colors.accent} />
        </View>
        <View style={styles.headerText}>
          <Text style={[styles.title, { color: colors.textPrimary }]}>Controllo automatico</Text>
          <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
            {runs ? riassuntoControllo(runs) : '…'}
          </Text>
        </View>
      </View>
      <Text style={[styles.description, { color: colors.textSecondary }]}>
        Ogni mattina ORA prova da sola promemoria, meteo, percorsi, avviso di partenza e punto del mattino.
        Se qualcosa non va, te lo dice lei.
      </Text>
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
});
