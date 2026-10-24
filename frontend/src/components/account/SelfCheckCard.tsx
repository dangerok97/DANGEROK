/**
 * What ORA found the last time it checked its own work.
 *
 * Every quarter of an hour ORA verifies that what it follows still has a
 * check on the calendar and that its notifications left on time, and repairs
 * what it safely can. This says so, in plain words, and says what it could
 * not fix.
 */
import { useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { api } from '@/src/api/client';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { SettingCard } from '@/src/components/account';

type Report = Awaited<ReturnType<typeof api.selfCheck>>;

export function selfCheckHeadline(report: Report | null): string {
  if (!report || !report.checked) return 'ORA non ha ancora fatto il primo controllo.';
  const open = (report.items || []).filter(i => !i.repaired).length;
  const fixed = (report.items || []).filter(i => i.repaired).length;
  if (open) return open === 1 ? 'C’è una cosa che ORA non è riuscita a sistemare da sola.' : `Ci sono ${open} cose che ORA non è riuscita a sistemare da sola.`;
  if (fixed) return fixed === 1 ? 'Tutto a posto: ORA ha sistemato da sola un problema.' : `Tutto a posto: ORA ha sistemato da sola ${fixed} problemi.`;
  return 'Tutto a posto.';
}

export function SelfCheckCard() {
  const { colors } = useTheme();
  const [report, setReport] = useState<Report | null>(null);

  useEffect(() => {
    let live = true;
    api.selfCheck().then(r => { if (live) setReport(r); }).catch(() => undefined);
    return () => { live = false; };
  }, []);

  if (!report) return null;
  const at = report.at ? new Date(report.at).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' }) : '';
  const healthy = report.checked && report.healthy !== false;
  return (
    <SettingCard testID="self-check-card">
      <View style={styles.header}>
        <Ionicons name={healthy ? 'shield-checkmark-outline' : 'alert-circle-outline'} size={20}
          color={healthy ? colors.success : colors.error} />
        <Text style={[styles.title, { color: colors.textPrimary }]}>Controllo di ORA</Text>
      </View>
      <Text style={[styles.body, { color: colors.textSecondary }]}>
        {selfCheckHeadline(report)}{at ? ` Ultimo controllo alle ${at}` : ''}
        {report.watches ? ` · ${report.watches} ${report.watches === 1 ? 'cosa seguita' : 'cose seguite'}` : ''}
      </Text>
      {(report.items || []).map((item, i) => (
        <Text key={i} style={[styles.body, { color: item.repaired ? colors.textSecondary : colors.error }]}>
          {item.repaired ? '✓ ' : '• '}{item.text}{item.repaired ? ' — sistemato' : ''}
        </Text>
      ))}
    </SettingCard>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.sm },
  title: { fontSize: 16, fontWeight: '650' as any },
  body: { fontSize: 13, lineHeight: 19, marginTop: 6 },
});
