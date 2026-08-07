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

/** Soft date + optional greeting; sync meta stays subordinate. */
export function HomeAmbientHeader({ online, lastSuccessAt }: Props) {
  const { colors } = useTheme();
  const greet = greetingForHour(new Date().getHours());

  return (
    <View style={styles.wrap} testID="home-ambient-header" accessibilityRole="header">
      <View style={styles.row}>
        <View style={styles.left}>
          <Text style={[styles.date, { color: colors.textPrimary }]}>{formatAmbientDate()}</Text>
          {greet ? (
            <Text style={[styles.greet, { color: colors.textSecondary }]}>{greet}</Text>
          ) : null}
        </View>
        <View style={styles.meta} testID="home-sync-meta">
          {!online ? (
            <Text style={[styles.metaText, { color: colors.warning }]}>Offline</Text>
          ) : lastSuccessAt ? (
            <Text
              style={[styles.metaText, { color: colors.textTertiary }]}
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
  wrap: { marginBottom: tokens.spacing.sm },
  row: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'space-between',
    gap: tokens.spacing.md,
  },
  left: { flex: 1, gap: 2 },
  date: {
    fontSize: tokens.typography.headline.fontSize,
    fontWeight: tokens.typography.headline.fontWeight,
    letterSpacing: tokens.typography.headline.letterSpacing,
    lineHeight: tokens.typography.headline.lineHeight,
  },
  greet: {
    fontSize: tokens.typography.caption.fontSize,
    lineHeight: tokens.typography.caption.lineHeight,
  },
  meta: { paddingBottom: 2, maxWidth: '40%', alignItems: 'flex-end' },
  metaText: {
    fontSize: tokens.typography.footnote.fontSize,
    fontWeight: '500',
    textAlign: 'right',
  },
});
