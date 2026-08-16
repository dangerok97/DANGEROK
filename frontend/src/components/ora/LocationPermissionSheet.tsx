/**
 * Quiet Premium location permission affordance — shown only when ORA needs location.
 */
import React from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';

import { LOCATION_PERMISSION_COPY } from '@/src/location/foregroundGeo';
import { useTheme } from '@/src/theme/ThemeProvider';

type Props = {
  visible: boolean;
  onAllow: () => void;
  onDeny: () => void;
};

export function LocationPermissionSheet({ visible, onAllow, onDeny }: Props) {
  const { colors } = useTheme();
  return (
    <Modal visible={visible} transparent animationType="fade" testID="location-permission-sheet">
      <View style={styles.backdrop}>
        <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <Text style={[styles.title, { color: colors.textPrimary }]}>Posizione</Text>
          <Text style={[styles.body, { color: colors.textSecondary }]}>
            {LOCATION_PERMISSION_COPY}
          </Text>
          <Text style={[styles.meta, { color: colors.textTertiary }]}>
            Solo mentre usi ORA. Lo sfondo non è disponibile.
          </Text>
          <View style={styles.row}>
            <Pressable
              onPress={onDeny}
              style={({ pressed }) => [styles.btn, pressed && styles.pressed]}
              testID="location-permission-deny"
            >
              <Text style={[styles.btnText, { color: colors.textSecondary }]}>Non ora</Text>
            </Pressable>
            <Pressable
              onPress={onAllow}
              style={({ pressed }) => [
                styles.btn,
                styles.btnPrimary,
                { backgroundColor: colors.textPrimary },
                pressed && styles.pressed,
              ]}
              testID="location-permission-allow"
            >
              <Text style={[styles.btnText, { color: colors.backgroundPrimary }]}>Durante l&apos;uso</Text>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.45)',
    justifyContent: 'center',
    padding: 24,
  },
  card: {
    borderRadius: 16,
    borderWidth: StyleSheet.hairlineWidth,
    padding: 20,
    gap: 12,
    maxWidth: 420,
    alignSelf: 'center',
    width: '100%',
  },
  title: {
    fontSize: 18,
    fontWeight: '600',
  },
  body: {
    fontSize: 15,
    lineHeight: 22,
  },
  meta: {
    fontSize: 13,
    lineHeight: 18,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 12,
    marginTop: 8,
  },
  btn: {
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderRadius: 10,
  },
  btnPrimary: {},
  btnText: {
    fontSize: 15,
    fontWeight: '600',
  },
  pressed: { opacity: 0.75 },
});
