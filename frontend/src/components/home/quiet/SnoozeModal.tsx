import { useMemo, useState } from 'react';
import { Modal, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import {
  HUMAN_SNOOZE_QUICK_CHOICES,
  describeSnoozeTarget,
} from '@/src/components/ui/humanTime';

type Props = {
  open: boolean;
  onClose: () => void;
  onSubmit: (until: string) => void;
};

/**
 * "Quando vuoi che te lo riproponga?"
 *
 * Was a text box labelled "Rimanda (ore)" with a default of 4 — a prototype
 * control that asked the user to convert their own day into an integer, and
 * exposed `defer_hours` in the process. Same contract on the wire (an absolute
 * ISO instant), asked in terms someone actually holds their day in.
 *
 * The custom picker is deliberately a plain date-time field rather than a new
 * calendar component: PX1.1 is foundations, and one honest input beats a
 * half-built picker.
 */
export function SnoozeModal({ open, onClose, onSubmit }: Props) {
  const { colors } = useTheme();
  const [custom, setCustom] = useState('');
  const [showCustom, setShowCustom] = useState(false);
  const now = useMemo(() => new Date(), [open]);

  const submitCustom = () => {
    const parsed = new Date(custom);
    if (Number.isNaN(parsed.getTime()) || parsed.getTime() <= Date.now()) return;
    onSubmit(parsed.toISOString());
  };

  const customValid = (() => {
    const parsed = new Date(custom);
    return !Number.isNaN(parsed.getTime()) && parsed.getTime() > Date.now();
  })();

  return (
    <Modal visible={open} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={[styles.scrim, { backgroundColor: colors.scrim }]} onPress={onClose}>
        <View
          style={[
            styles.card,
            { backgroundColor: colors.surfaceElevated, borderColor: colors.border },
          ]}
          onStartShouldSetResponder={() => true}
          accessibilityViewIsModal
          testID="snooze-modal"
        >
          <Text style={[styles.title, { color: colors.textPrimary }]} accessibilityRole="header">
            Quando vuoi che te lo riproponga?
          </Text>

          {HUMAN_SNOOZE_QUICK_CHOICES.map((choice) => {
            const target = choice.resolve(now);
            return (
              <Pressable
                key={choice.id}
                testID={`snooze-${choice.id}`}
                onPress={() => target && onSubmit(target.toISOString())}
                accessibilityRole="button"
                accessibilityLabel={
                  target ? `${choice.label}, ${describeSnoozeTarget(target, now)}` : choice.label
                }
                style={({ pressed }) => [
                  styles.option,
                  { borderColor: colors.border },
                  pressed && { backgroundColor: colors.backgroundSecondary },
                ]}
              >
                <Text style={[styles.optionLabel, { color: colors.textPrimary }]}>
                  {choice.label}
                </Text>
                {target ? (
                  <Text style={[styles.optionMeta, { color: colors.textTertiary }]}>
                    {describeSnoozeTarget(target, now)}
                  </Text>
                ) : null}
              </Pressable>
            );
          })}

          {showCustom ? (
            <View style={styles.customBlock}>
              <TextInput
                style={[
                  styles.input,
                  {
                    borderColor: colors.borderStrong,
                    color: colors.textPrimary,
                    backgroundColor: colors.backgroundSecondary,
                  },
                ]}
                value={custom}
                onChangeText={setCustom}
                placeholder="2026-09-01 09:00"
                placeholderTextColor={colors.placeholder}
                testID="snooze-custom-input"
                accessibilityLabel="Data e ora"
                autoCapitalize="none"
              />
              <Pressable
                style={({ pressed }) => [
                  styles.confirm,
                  { backgroundColor: customValid ? colors.accent : colors.border },
                  pressed && { opacity: 0.8 },
                ]}
                onPress={submitCustom}
                disabled={!customValid}
                testID="snooze-custom-confirm"
                accessibilityRole="button"
                accessibilityState={{ disabled: !customValid }}
              >
                <Text
                  style={[
                    styles.confirmLabel,
                    { color: customValid ? colors.onAccent : colors.textTertiary },
                  ]}
                >
                  Conferma
                </Text>
              </Pressable>
            </View>
          ) : (
            <Pressable
              testID="snooze-custom"
              onPress={() => setShowCustom(true)}
              accessibilityRole="button"
              style={({ pressed }) => [
                styles.option,
                { borderColor: colors.border },
                pressed && { backgroundColor: colors.backgroundSecondary },
              ]}
            >
              <Text style={[styles.optionLabel, { color: colors.textPrimary }]}>
                Scegli data e ora
              </Text>
            </Pressable>
          )}
        </View>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  scrim: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 24 },
  card: {
    borderRadius: tokens.radius.lg,
    padding: tokens.spacing.xl,
    gap: tokens.spacing.sm,
    borderWidth: StyleSheet.hairlineWidth,
    width: '100%',
    // Bounded on desktop — a dialog is a focused question, not a page.
    maxWidth: 420,
  },
  title: {
    fontSize: 17,
    fontWeight: '700',
    lineHeight: 24,
    marginBottom: tokens.spacing.sm,
  },
  option: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: tokens.spacing.md,
    minHeight: tokens.touch.min,
    paddingVertical: tokens.spacing.md,
    paddingHorizontal: tokens.spacing.lg,
    borderRadius: tokens.radius.md,
    borderWidth: StyleSheet.hairlineWidth,
  },
  optionLabel: { fontSize: 15, fontWeight: '500' },
  optionMeta: { fontSize: 13 },
  customBlock: { gap: tokens.spacing.sm },
  input: {
    borderWidth: 1,
    borderRadius: tokens.radius.md,
    paddingHorizontal: tokens.spacing.lg,
    minHeight: tokens.touch.min,
    fontSize: 16,
  },
  confirm: {
    minHeight: tokens.touch.min,
    borderRadius: tokens.radius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  confirmLabel: { fontSize: 15, fontWeight: '600' },
});
