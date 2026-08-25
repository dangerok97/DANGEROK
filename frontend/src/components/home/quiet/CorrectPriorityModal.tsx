import { Modal, Pressable, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { HomePriorityBand } from '@/src/api/client';

type Props = {
  open: boolean;
  onClose: () => void;
  onPick: (p: HomePriorityBand) => void;
  /** What the situation is set to now, so the dialog opens on a known state. */
  current?: HomePriorityBand | null;
};

/**
 * One question, one dimension: how soon this should come back to the front.
 *
 * The previous version mixed three incompatible ideas in one list — urgency
 * (Critico), timing (Oggi / Questa settimana / Più avanti) and status
 * (In attesa) — so choosing meant first deciding what kind of thing was being
 * asked. "In attesa" is a state something is *in*, never a priority a person
 * assigns, and deferring already has its own action (Rimanda); both are gone
 * from here.
 */
const OPTIONS: Array<{ band: HomePriorityBand; label: string; detail: string }> = [
  { band: 'critical', label: 'Critico', detail: 'Richiede attenzione immediata' },
  { band: 'today', label: 'Oggi', detail: 'È importante occuparsene oggi' },
  { band: 'this_week', label: 'Questa settimana', detail: 'Può aspettare qualche giorno' },
  { band: 'later', label: 'Più avanti', detail: 'Non serve occuparsene adesso' },
];

/** Below this a centred dialog fights the keyboard and the thumb: use a sheet. */
const SHEET_MAX_WIDTH = 600;
const DIALOG_WIDTH = 480;

export function CorrectPriorityModal({ open, onClose, onPick, current }: Props) {
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const sheet = width < SHEET_MAX_WIDTH;

  return (
    <Modal visible={open} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable
        style={[
          styles.scrim,
          { backgroundColor: colors.scrim },
          sheet ? styles.scrimSheet : styles.scrimCentred,
        ]}
        onPress={onClose}
        accessibilityLabel="Chiudi"
      >
        <View
          style={[
            styles.card,
            sheet ? styles.cardSheet : [styles.cardDialog, { width: DIALOG_WIDTH }],
            { backgroundColor: colors.surfaceElevated, borderColor: colors.border },
          ]}
          // Presses inside the dialog must not reach the scrim behind it.
          onStartShouldSetResponder={() => true}
          accessibilityViewIsModal
          testID="correct-priority-dialog"
        >
          <View style={styles.head}>
            <View style={styles.headText}>
              <Text
                style={[styles.title, { color: colors.textPrimary }]}
                accessibilityRole="header"
              >
                Cambia priorità
              </Text>
              <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
                Quando deve tornare in primo piano?
              </Text>
            </View>
            <Pressable
              onPress={onClose}
              hitSlop={8}
              style={({ pressed }) => [styles.close, pressed && styles.pressed]}
              accessibilityRole="button"
              accessibilityLabel="Chiudi"
              testID="correct-priority-close"
            >
              <Ionicons name="close" size={20} color={colors.textTertiary} />
            </Pressable>
          </View>

          <View style={styles.options}>
            {OPTIONS.map((o) => {
              const selected = current === o.band;
              return (
                <Pressable
                  key={o.band}
                  onPress={() => onPick(o.band)}
                  style={({ pressed, hovered }: any) => [
                    styles.row,
                    {
                      backgroundColor: selected
                        ? colors.accentMuted
                        : hovered
                          ? colors.backgroundSecondary
                          : 'transparent',
                      borderColor: selected ? colors.accent : colors.border,
                    },
                    pressed && styles.pressed,
                  ]}
                  accessibilityRole="radio"
                  accessibilityState={{ selected, checked: selected }}
                  aria-checked={selected}
                  accessibilityLabel={`${o.label}. ${o.detail}`}
                  testID={`correct-${o.band}`}
                >
                  <View style={styles.rowText}>
                    <Text
                      style={[
                        styles.rowLabel,
                        { color: selected ? colors.accent : colors.textPrimary },
                      ]}
                    >
                      {o.label}
                    </Text>
                    <Text style={[styles.rowDetail, { color: colors.textSecondary }]}>
                      {o.detail}
                    </Text>
                  </View>
                  {selected ? (
                    <Ionicons name="checkmark-circle" size={20} color={colors.accent} />
                  ) : null}
                </Pressable>
              );
            })}
          </View>
        </View>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  scrim: { flex: 1 },
  scrimCentred: { justifyContent: 'center', alignItems: 'center', padding: tokens.spacing.xl },
  scrimSheet: { justifyContent: 'flex-end' },
  card: {
    borderWidth: StyleSheet.hairlineWidth,
    padding: tokens.spacing.xl,
    gap: tokens.spacing.lg,
  },
  cardDialog: { borderRadius: tokens.radius.xl, maxWidth: '100%' },
  cardSheet: {
    borderTopLeftRadius: tokens.radius.xl,
    borderTopRightRadius: tokens.radius.xl,
    paddingBottom: tokens.spacing.xxl,
  },
  head: { flexDirection: 'row', alignItems: 'flex-start', gap: tokens.spacing.md },
  headText: { flex: 1, gap: 4 },
  title: { fontSize: 19, fontWeight: '700', letterSpacing: -0.3 },
  subtitle: { fontSize: 14, lineHeight: 20 },
  close: {
    width: tokens.touch.min, height: tokens.touch.min,
    alignItems: 'center', justifyContent: 'center',
    marginTop: -10, marginRight: -12,
  },
  options: { gap: tokens.spacing.sm },
  row: {
    flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.md,
    paddingHorizontal: tokens.spacing.lg,
    paddingVertical: tokens.spacing.md,
    minHeight: 60,
  },
  rowText: { flex: 1, gap: 2 },
  rowLabel: { fontSize: 15, fontWeight: '600' },
  rowDetail: { fontSize: 13, lineHeight: 18 },
  pressed: { opacity: 0.7 },
});
