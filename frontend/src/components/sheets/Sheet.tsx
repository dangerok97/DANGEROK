import { View, Text, StyleSheet, Pressable, Modal, ScrollView, Platform } from 'react-native';
import Animated, { FadeIn, FadeOut, SlideInDown } from 'react-native-reanimated';
import { tokens } from '@/src/theme/tokens';

type Props = {
  open: boolean;
  onClose: () => void;
  title?: string;
  testID?: string;
  children: React.ReactNode;
};

export function Sheet({ open, onClose, title, testID, children }: Props) {
  return (
    <Modal visible={!!open} transparent animationType="none" onRequestClose={onClose} statusBarTranslucent>
      {open ? (
        <>
          <Animated.View
            entering={FadeIn.duration(tokens.motion.fast)}
            exiting={FadeOut.duration(tokens.motion.fast)}
            style={styles.backdrop}
          >
            <Pressable style={{ flex: 1 }} onPress={onClose} accessibilityLabel="Chiudi" accessibilityRole="button" />
          </Animated.View>
          <Animated.View
            entering={SlideInDown.duration(tokens.motion.slow).springify().damping(18)}
            exiting={FadeOut.duration(tokens.motion.fast)}
            style={styles.sheet}
            testID={testID}
          >
            <View style={styles.grab} />
            {title && <Text style={styles.title} accessibilityRole="header">{title}</Text>}
            <ScrollView showsVerticalScrollIndicator={false}>{children}</ScrollView>
          </Animated.View>
        </>
      ) : null}
    </Modal>
  );
}

export function SheetSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  backdrop: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: tokens.color.scrim },
  sheet: {
    position: 'absolute', bottom: 0, left: 0, right: 0,
    maxHeight: '85%',
    backgroundColor: tokens.color.surfaceSecondary,
    borderTopLeftRadius: tokens.radius.xl,
    borderTopRightRadius: tokens.radius.xl,
    padding: tokens.spacing.lg,
    paddingBottom: Platform.OS === 'ios' ? tokens.spacing.xxl : tokens.spacing.xxl,
    borderWidth: 1,
    borderColor: tokens.color.border,
    borderBottomWidth: 0,
  },
  grab: { width: 40, height: 4, backgroundColor: tokens.color.borderStrong, borderRadius: 2, alignSelf: 'center', marginBottom: 12 },
  title: { fontSize: 18, fontWeight: '700', color: tokens.color.onSurface, marginBottom: 12 },
  section: { marginTop: 16, gap: 6 },
  sectionTitle: { fontSize: 11, color: tokens.color.onSurfaceMuted, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4, fontWeight: '600' },
});
