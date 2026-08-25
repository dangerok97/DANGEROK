import { ActivityIndicator, Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { Avatar } from '@/src/shell';
import { useProfilePhoto } from '@/src/components/profile/ProfilePhotoSection';

/**
 * Changing your picture, on the page where your picture is.
 *
 * The name and the email on the card above come from whichever way you signed
 * in and there is no endpoint in ORA that edits either, so this dialog does
 * not pretend to be a profile editor — it does the one thing that is real, and
 * says where the rest comes from.
 */
export function PhotoDialog({
  open,
  onClose,
  accessLabel,
}: {
  open: boolean;
  onClose: () => void;
  /** How this person signs in — the source of their name and email. */
  accessLabel?: string | null;
}) {
  const { colors } = useTheme();
  const { user, busy, error, pick, remove } = useProfilePhoto();

  return (
    <Modal visible={open} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable
        style={[styles.scrim, { backgroundColor: colors.scrim }]}
        onPress={onClose}
        accessibilityLabel="Chiudi"
      >
        <View
          style={[
            styles.dialog,
            { backgroundColor: colors.surfaceElevated, borderColor: colors.border },
          ]}
          onStartShouldSetResponder={() => true}
          accessibilityViewIsModal
          testID="account-photo-dialog"
        >
          <View style={styles.head}>
            <Text
              style={[styles.title, { color: colors.textPrimary }]}
              accessibilityRole="header"
              aria-level={2}
            >
              La tua foto
            </Text>
            <Pressable
              onPress={onClose}
              hitSlop={8}
              style={({ pressed }) => [styles.close, pressed && styles.pressed]}
              accessibilityRole="button"
              accessibilityLabel="Chiudi"
              testID="account-photo-close"
            >
              <Ionicons name="close" size={20} color={colors.textTertiary} />
            </Pressable>
          </View>

          <View style={styles.body}>
            <Avatar name={user?.name} picture={user?.picture} size={72} />
            <Text style={[styles.hint, { color: colors.textSecondary }]}>
              {user?.picture
                ? 'Compare accanto al tuo nome dentro ORA.'
                : 'Finora ORA usa le tue iniziali.'}
            </Text>
          </View>

          <View style={styles.actions}>
            <Pressable
              onPress={() => void pick()}
              disabled={!!busy}
              style={({ pressed }) => [
                styles.primary,
                { backgroundColor: colors.accent },
                (pressed || !!busy) && styles.pressed,
              ]}
              accessibilityRole="button"
              testID="account-photo-change"
            >
              {busy === 'upload' ? (
                <ActivityIndicator color={colors.onAccent} size="small" />
              ) : (
                <Text style={[styles.primaryLabel, { color: colors.onAccent }]}>
                  {user?.picture ? 'Cambia foto' : 'Carica foto'}
                </Text>
              )}
            </Pressable>
            {user?.picture ? (
              <Pressable
                onPress={() => void remove()}
                disabled={!!busy}
                style={({ pressed }) => [
                  styles.ghost,
                  { borderColor: colors.border },
                  (pressed || !!busy) && styles.pressed,
                ]}
                accessibilityRole="button"
                testID="account-photo-remove"
              >
                {busy === 'remove' ? (
                  <ActivityIndicator color={colors.textSecondary} size="small" />
                ) : (
                  <Text style={[styles.ghostLabel, { color: colors.textSecondary }]}>Rimuovi</Text>
                )}
              </Pressable>
            ) : null}
          </View>

          {error ? (
            <Text style={[styles.error, { color: colors.error }]} testID="account-photo-error">
              {error}
            </Text>
          ) : null}

          {accessLabel ? (
            <Text style={[styles.footnote, { color: colors.textTertiary }]}>
              {`Nome ed email arrivano da come accedi a ORA (${accessLabel}).`}
            </Text>
          ) : null}
        </View>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  scrim: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: tokens.spacing.xl },
  dialog: {
    width: 420, maxWidth: '100%',
    borderRadius: tokens.radius.xl, borderWidth: StyleSheet.hairlineWidth,
    padding: tokens.spacing.xl, gap: tokens.spacing.md,
  },
  head: { flexDirection: 'row', alignItems: 'flex-start', gap: tokens.spacing.md },
  title: { fontSize: 19, fontWeight: '700', flex: 1, letterSpacing: -0.3 },
  close: {
    width: tokens.touch.min, height: tokens.touch.min,
    alignItems: 'center', justifyContent: 'center', marginTop: -10, marginRight: -12,
  },
  body: { flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.lg },
  hint: { flex: 1, fontSize: 14, lineHeight: 20 },
  actions: { flexDirection: 'row', gap: tokens.spacing.sm, flexWrap: 'wrap' },
  primary: {
    minHeight: tokens.touch.min, paddingHorizontal: tokens.spacing.xl,
    borderRadius: tokens.radius.md, alignItems: 'center', justifyContent: 'center',
  },
  primaryLabel: { fontSize: 14, fontWeight: '600' },
  ghost: {
    minHeight: tokens.touch.min, paddingHorizontal: tokens.spacing.lg,
    borderRadius: tokens.radius.md, borderWidth: StyleSheet.hairlineWidth,
    alignItems: 'center', justifyContent: 'center',
  },
  ghostLabel: { fontSize: 14, fontWeight: '600' },
  error: { fontSize: 13, lineHeight: 19 },
  footnote: { fontSize: 12, lineHeight: 17 },
  pressed: { opacity: 0.75 },
});
