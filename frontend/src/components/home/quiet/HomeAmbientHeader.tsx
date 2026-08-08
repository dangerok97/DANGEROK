import { View, Text, StyleSheet } from 'react-native';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { formatRelativeAgo } from '@/src/utils/labels';

type Props = {
  online: boolean;
  lastSuccessAt: Date | null;
};

function formatAmbientDate(d = new Date()): string {
  const raw = d.toLocaleDateString('it-IT', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });
  return raw.charAt(0).toUpperCase() + raw.slice(1);
}

function greetingForHour(h: number): string | null {
  if (h >= 5 && h < 12) return 'Buongiorno';
  if (h >= 12 && h < 18) return 'Buon pomeriggio';
  if (h >= 18 && h < 23) return 'Buonasera';
  return null;
}

/** Fresh sync (< 90s) stays almost invisible — only Offline is assertive. */
function syncLabel(online: boolean, lastSuccessAt: Date | null): string | null {
  if (!online) return 'Offline';
  if (!lastSuccessAt) return null;
  const ageMs = Date.now() - lastSuccessAt.getTime();
  if (ageMs < 90_000) return null;
  return `Aggiornato ${formatRelativeAgo(lastSuccessAt)}`;
}

/** Editorial date — refined, not a page title. */
export function HomeAmbientHeader({ online, lastSuccessAt }: Props) {
  const { colors } = useTheme();
  const greet = greetingForHour(new Date().getHours());
  const sync = syncLabel(online, lastSuccessAt);

  return (
    <View style={styles.wrap} testID="home-ambient-header" accessibilityRole="header">
      <View style={styles.row}>
        <View style={styles.left}>
          <Text style={[styles.date, { color: colors.textSecondary }]}>{formatAmbientDate()}</Text>
          {greet ? (
            <Text style={[styles.greet, { color: colors.textTertiary }]}>{greet}</Text>
          ) : null}
        </View>
        <View style={styles.meta} testID="home-sync-meta">
          {sync ? (
            <Text
              style={[
                styles.metaText,
                { color: online ? colors.textTertiary : colors.warning },
              ]}
              accessibilityLabel={
                online && lastSuccessAt
                  ? `Ultimo aggiornamento ${formatRelativeAgo(lastSuccessAt)}`
                  : 'Offline'
              }
            >
              {sync}
            </Text>
          ) : online && lastSuccessAt ? (
            <Text
              style={{ position: 'absolute', width: 1, height: 1, opacity: 0 }}
              accessibilityLabel={`Ultimo aggiornamento ${formatRelativeAgo(lastSuccessAt)}`}
            >
              Aggiornato {formatRelativeAgo(lastSuccessAt)}
            </Text>
          ) : null}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginBottom: tokens.spacing.xs },
  row: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'space-between',
    gap: tokens.spacing.md,
  },
  left: { flex: 1, gap: 2 },
  date: {
    fontSize: tokens.typography.body.fontSize,
    fontWeight: '500',
    letterSpacing: -0.2,
    lineHeight: tokens.typography.body.lineHeight,
  },
  greet: {
    fontSize: tokens.typography.footnote.fontSize,
    lineHeight: 16,
    fontWeight: '400',
  },
  meta: { paddingBottom: 2, maxWidth: '42%', alignItems: 'flex-end' },
  metaText: {
    fontSize: 11,
    fontWeight: '400',
    textAlign: 'right',
  },
});
