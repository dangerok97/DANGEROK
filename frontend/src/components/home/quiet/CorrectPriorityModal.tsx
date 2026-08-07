import { Modal, Pressable, Text, View, StyleSheet } from 'react-native';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { HomePriorityBand } from '@/src/api/client';

type Props = {
  open: boolean;
  onClose: () => void;
  onPick: (p: HomePriorityBand) => void;
};

const OPTS: HomePriorityBand[] = ['critical', 'today', 'this_week', 'waiting', 'later'];
const LABELS: Record<HomePriorityBand, string> = {
  critical: 'Critico',
  today: 'Oggi',
  this_week: 'Questa settimana',
  waiting: 'In attesa',
  later: 'Più avanti',
};

export function CorrectPriorityModal({ open, onClose, onPick }: Props) {
  const { colors } = useTheme();
  return (
    <Modal visible={open} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={[styles.scrim, { backgroundColor: colors.scrim }]} onPress={onClose}>
        <View
          style={[styles.card, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}
          onStartShouldSetResponder={() => true}
        >
          <Text style={[styles.title, { color: colors.textPrimary }]}>Correggi priorità</Text>
          {OPTS.map((p) => (
            <Pressable
              key={p}
              style={[styles.row, { backgroundColor: colors.backgroundSecondary }]}
              onPress={() => onPick(p)}
              testID={`correct-${p}`}
              accessibilityRole="button"
              accessibilityLabel={LABELS[p]}
            >
              <Text style={[styles.rowText, { color: colors.textPrimary }]}>{LABELS[p]}</Text>
            </Pressable>
          ))}
        </View>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  scrim: { flex: 1, justifyContent: 'center', padding: 24 },
  card: {
    borderRadius: tokens.radius.lg,
    padding: 16,
    gap: 8,
    borderWidth: StyleSheet.hairlineWidth,
  },
  title: { fontSize: 16, fontWeight: '700', marginBottom: 4 },
  row: {
    paddingVertical: 12,
    paddingHorizontal: 8,
    borderRadius: tokens.radius.md,
    minHeight: tokens.touch.min,
    justifyContent: 'center',
  },
  rowText: { fontSize: 14, fontWeight: '600' },
});
