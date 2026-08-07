import { View, Text, StyleSheet, Pressable } from 'react-native';
import { useRouter } from 'expo-router';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { HomeItem } from '@/src/api/client';
import { navigateHomeAction } from '@/src/components/home/v2/homeNav';
import { triggerHaptic } from '@/src/theme/haptics';

type Props = {
  item: HomeItem;
  onResume?: () => void;
};

/** Continuity — “Dove avevo lasciato?” — light, not a hero. */
export function ContinueSection({ item, onResume }: Props) {
  const { colors } = useTheme();
  const router = useRouter();
  if (!item) return null;
  const action = item.actions?.find((a) => a.kind === 'resume') || item.actions?.[0];

  return (
    <View style={[styles.wrap, { borderTopColor: colors.divider }]} testID="resume-card">
      <Text style={[styles.h, { color: colors.textTertiary }]} accessibilityRole="header">
        Continua
      </Text>
      <Text style={[styles.title, { color: colors.textPrimary }]} numberOfLines={2}>
        {item.title}
      </Text>
      {item.description ? (
        <Text style={[styles.desc, { color: colors.textSecondary }]} numberOfLines={2}>
          {item.description}
        </Text>
      ) : null}
      <Pressable
        testID="btn-resume"
        accessibilityRole="button"
        accessibilityLabel={action?.label || 'Continua'}
        style={({ pressed }) => [
          styles.btn,
          {
            borderColor: colors.borderStrong,
            opacity: pressed ? 0.8 : 1,
            transform: [{ scale: pressed ? tokens.motion.pressScale : 1 }],
          },
        ]}
        onPress={async () => {
          void triggerHaptic('selection');
          if (action) await navigateHomeAction(router, action, item);
          onResume?.();
        }}
      >
        <Text style={[styles.btnText, { color: colors.accent }]}>
          {action?.label || 'Continua'}
        </Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: tokens.spacing.xs,
    paddingTop: tokens.spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  h: {
    fontSize: tokens.typography.label.fontSize,
    fontWeight: '600',
    letterSpacing: 0.2,
  },
  title: {
    fontSize: tokens.typography.body.fontSize,
    fontWeight: '600',
  },
  desc: {
    fontSize: tokens.typography.caption.fontSize,
    lineHeight: 18,
  },
  btn: {
    alignSelf: 'flex-start',
    minHeight: tokens.touch.min,
    paddingHorizontal: 14,
    justifyContent: 'center',
    borderRadius: tokens.radius.full,
    borderWidth: StyleSheet.hairlineWidth,
    marginTop: 4,
  },
  btnText: { fontSize: 14, fontWeight: '600' },
});
