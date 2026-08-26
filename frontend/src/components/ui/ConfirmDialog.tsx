import { useEffect, useRef } from 'react';
import { Modal, Platform, Pressable, StyleSheet, Text, View } from 'react-native';

import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { ActionBtn } from './ActionBtn';

/**
 * "Are you sure?", once, for the whole product.
 *
 * There were two shapes of this before: a real `Modal` for disconnecting a
 * calendar, and an absolutely-positioned overlay for the same job elsewhere.
 * The overlay looked identical and behaved differently — Escape did nothing
 * and the page behind it kept its place in the tab order, so a keyboard user
 * could walk straight past the question and press the button it was asking
 * about. This is the `Modal` version, and it is the only one.
 *
 * The destructive action is red and on the right, the way out is plain and on
 * the left, and the dialog says what will happen rather than shouting.
 */
export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  cancelLabel = 'Annulla',
  destructive,
  busy,
  onCancel,
  onConfirm,
  testID,
  confirmTestID,
}: {
  open: boolean;
  title: string;
  body?: string;
  confirmLabel: string;
  cancelLabel?: string;
  destructive?: boolean;
  busy?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
  testID?: string;
  confirmTestID?: string;
}) {
  const { colors } = useTheme();
  const card = useRef<View | null>(null);

  /**
   * Start inside the question.
   *
   * Native `Modal` moves focus for us; on web it does not, so a keyboard user
   * would otherwise still be standing wherever they were on the page behind.
   * Focusing the card puts them at the top of the dialog, and Escape — which
   * `onRequestClose` already handles — takes them back out.
   */
  useEffect(() => {
    if (!open || Platform.OS !== 'web') return;
    const node = card.current as unknown as HTMLElement | null;
    if (!node) return;
    const id = setTimeout(() => node.focus?.(), 30);
    return () => clearTimeout(id);
  }, [open]);

  if (!open) return null;

  return (
    <Modal visible transparent animationType="fade" onRequestClose={onCancel}>
      <Pressable
        style={[styles.scrim, { backgroundColor: colors.scrim }]}
        onPress={busy ? undefined : onCancel}
        accessibilityLabel={cancelLabel}
      >
        <View
          ref={card}
          style={[
            styles.card,
            { backgroundColor: colors.surfaceElevated, borderColor: colors.border },
          ]}
          onStartShouldSetResponder={() => true}
          accessibilityViewIsModal
          {...(Platform.OS === 'web' ? ({ tabIndex: -1, 'aria-modal': true, role: 'dialog' } as any) : null)}
          testID={testID}
        >
          <Text
            style={[styles.title, { color: colors.textPrimary }]}
            accessibilityRole="header"
            aria-level={2}
          >
            {title}
          </Text>
          {body ? (
            <Text style={[styles.body, { color: colors.textSecondary }]}>{body}</Text>
          ) : null}
          <View style={styles.row}>
            <ActionBtn label={cancelLabel} icon="close" onPress={onCancel} disabled={busy} />
            <ActionBtn
              variant={destructive ? 'danger' : 'default'}
              primary={!destructive}
              icon={destructive ? 'trash-outline' : 'checkmark'}
              label={confirmLabel}
              onPress={onConfirm}
              loading={busy}
              testID={confirmTestID}
            />
          </View>
        </View>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  scrim: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: tokens.spacing.xl },
  card: {
    width: 420, maxWidth: '100%',
    borderRadius: tokens.radius.xl, borderWidth: StyleSheet.hairlineWidth,
    padding: tokens.spacing.xl, gap: tokens.spacing.sm,
  },
  title: { fontSize: 18, fontWeight: '700', letterSpacing: -0.3 },
  body: { fontSize: 14, lineHeight: 20 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: tokens.spacing.sm, marginTop: tokens.spacing.md },
});
