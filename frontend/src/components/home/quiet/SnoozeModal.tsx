import { useState } from 'react';
import { Modal, Pressable, Text, TextInput, View, StyleSheet } from 'react-native';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

type Props = {
  open: boolean;
  onClose: () => void;
  onSubmit: (until: string) => void;
};

export function SnoozeModal({ open, onClose, onSubmit }: Props) {
  const { colors, isDark } = useTheme();
  const [hours, setHours] = useState('4');

  return (
    <Modal visible={open} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={[styles.scrim, { backgroundColor: colors.scrim }]} onPress={onClose}>
        <View
          style={[styles.card, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}
          onStartShouldSetResponder={() => true}
        >
          <Text style={[styles.title, { color: colors.textPrimary }]}>Rimanda (ore)</Text>
          <TextInput
            style={[
              styles.input,
              {
                borderColor: colors.borderStrong,
                color: colors.textPrimary,
                backgroundColor: colors.backgroundSecondary,
              },
            ]}
            value={hours}
            onChangeText={setHours}
            keyboardType="number-pad"
            keyboardAppearance={isDark ? 'dark' : 'light'}
            testID="snooze-hours"
            accessibilityLabel="Ore di rinvio"
          />
          <Pressable
            style={[styles.row, { backgroundColor: colors.accent }]}
            onPress={() => {
              const h = Math.max(1, parseInt(hours || '4', 10) || 4);
              const until = new Date(Date.now() + h * 3600_000).toISOString();
              onSubmit(until);
            }}
            testID="snooze-confirm"
            accessibilityRole="button"
          >
            <Text style={[styles.confirm, { color: colors.onAccent }]}>Conferma</Text>
          </Pressable>
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
  input: {
    borderWidth: 1,
    borderRadius: tokens.radius.md,
    padding: 12,
    minHeight: tokens.touch.min,
    fontSize: 16,
  },
  row: {
    paddingVertical: 12,
    paddingHorizontal: 8,
    borderRadius: tokens.radius.md,
    minHeight: tokens.touch.min,
    alignItems: 'center',
    justifyContent: 'center',
  },
  confirm: { fontSize: 14, fontWeight: '600' },
});
