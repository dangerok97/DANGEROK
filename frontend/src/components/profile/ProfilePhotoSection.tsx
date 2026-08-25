import { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import * as DocumentPicker from 'expo-document-picker';

import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { api } from '@/src/api/client';
import { useAuth } from '@/src/contexts/AuthContext';
import { Avatar } from '@/src/shell';
import { haptic } from '@/src/utils/haptic';

/**
 * Profile photo — chosen by the user, changed by the user, removed by the user.
 *
 * Deliberately no technical surface: no URL field, no "profile_image_url", no
 * file path. A person changing their own picture should see their picture and
 * a way to change it.
 *
 * Uses `expo-document-picker` filtered to images — the same picker the
 * Documenti upload already relies on, so there is one file-choosing path in
 * the product rather than two. It resolves to a file input on web and to the
 * system picker on device, which is what keeps this iOS-ready: swapping in the
 * photo library later is a change inside this function, not to the flow.
 */
/**
 * The photo, and the three things that can happen to it.
 *
 * Extracted so the account surface can offer the same upload / change / remove
 * from its identity card without a second copy of the flow — there is one
 * avatar store and one path to it, and this is that path.
 */
export function useProfilePhoto() {
  const { user, refresh } = useAuth();
  const [busy, setBusy] = useState<'upload' | 'remove' | null>(null);
  const [error, setError] = useState<string | null>(null);

  const pick = async () => {
    haptic('tap');
    setError(null);
    try {
      const res = await DocumentPicker.getDocumentAsync({
        type: 'image/*',
        multiple: false,
        copyToCacheDirectory: true,
      });
      if (res.canceled || !res.assets?.[0]) return;

      const asset = res.assets[0];
      setBusy('upload');
      await api.uploadAvatar({
        uri: asset.uri,
        name: asset.name || 'foto-profilo.jpg',
        type: asset.mimeType || 'image/jpeg',
      });
      await refresh();
      haptic('success');
    } catch (e: any) {
      haptic('error');
      setError(e?.message || 'Non è stato possibile salvare la foto.');
    } finally {
      setBusy(null);
    }
  };

  const remove = async () => {
    haptic('warning');
    setError(null);
    setBusy('remove');
    try {
      await api.removeAvatar();
      await refresh();
      haptic('success');
    } catch (e: any) {
      setError(e?.message || 'Non è stato possibile rimuovere la foto.');
    } finally {
      setBusy(null);
    }
  };

  return { user, busy, error, pick, remove };
}

export function ProfilePhotoSection() {
  const { colors } = useTheme();
  const { user, busy, error, pick, remove } = useProfilePhoto();

  return (
    <View testID="profile-photo-section" style={styles.wrap}>
      <Text style={[styles.label, { color: colors.textSecondary }]}>FOTO PROFILO</Text>
      <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
        <Avatar name={user?.name} picture={user?.picture} size={64} />

        <View style={styles.textCol}>
          <Text style={[styles.title, { color: colors.textPrimary }]}>
            {user?.picture ? 'La tua foto' : 'Nessuna foto'}
          </Text>
          <Text style={[styles.hint, { color: colors.textTertiary }]}>
            {user?.picture
              ? 'Compare accanto al tuo nome dentro ORA.'
              : 'Finora ORA usa le tue iniziali.'}
          </Text>
        </View>

        <View style={styles.actions}>
          <Pressable
            onPress={pick}
            disabled={!!busy}
            style={({ pressed }) => [
              styles.primary,
              { backgroundColor: colors.accent },
              pressed && styles.pressed,
              !!busy && styles.disabled,
            ]}
            accessibilityRole="button"
            testID="profile-photo-change"
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
              onPress={remove}
              disabled={!!busy}
              style={({ pressed }) => [styles.ghost, pressed && styles.pressed, !!busy && styles.disabled]}
              accessibilityRole="button"
              testID="profile-photo-remove"
            >
              <Text style={[styles.ghostLabel, { color: colors.textSecondary }]}>Rimuovi</Text>
            </Pressable>
          ) : null}
        </View>
      </View>

      {error ? (
        <Text style={[styles.error, { color: colors.error }]} testID="profile-photo-error">
          {error}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: tokens.spacing.sm },
  label: { fontSize: 11, fontWeight: '700', letterSpacing: 1.2, paddingHorizontal: 4 },
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: tokens.spacing.lg,
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    padding: tokens.spacing.lg,
    flexWrap: 'wrap',
  },
  textCol: { flex: 1, minWidth: 140, gap: 2 },
  title: { fontSize: 15, fontWeight: '600' },
  hint: { fontSize: 13, lineHeight: 18 },
  actions: { flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.sm },
  primary: {
    minHeight: tokens.touch.min,
    paddingHorizontal: tokens.spacing.xl,
    borderRadius: tokens.radius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryLabel: { fontSize: 14, fontWeight: '600' },
  ghost: {
    minHeight: tokens.touch.min,
    paddingHorizontal: tokens.spacing.lg,
    justifyContent: 'center',
  },
  ghostLabel: { fontSize: 14, fontWeight: '500' },
  error: { fontSize: 13, paddingHorizontal: 4 },
  pressed: { opacity: 0.75 },
  disabled: { opacity: 0.5 },
});
