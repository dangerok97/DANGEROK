import {
  View, Text, StyleSheet, Pressable, ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { HomeActionDef, HomeItem } from '@/src/api/client';
import { isGuidedAction, navigateHomeAction } from '@/src/components/home/v2/homeNav';

type Props = {
  item: HomeItem;
  busy?: string | null;
  onAction: (action: HomeActionDef) => void | Promise<void>;
};

type Tier = 'primary' | 'secondary' | 'tertiary';

function tierFor(action: HomeActionDef, index: number, primaryId?: string): Tier {
  if (action.kind === 'snooze' || action.kind === 'ignore' || action.kind === 'correct') {
    return 'tertiary';
  }
  if (action.primary || action.id === primaryId || index === 0) return 'primary';
  return 'secondary';
}

/**
 * CTA hierarchy for Daily Focus — one filled primary, light outline secondary, ghost tertiary.
 * Preserves home-action-* testIDs.
 */
export function FocusActions({ item, busy, onAction }: Props) {
  const { colors } = useTheme();
  const router = useRouter();
  const actions = item.actions || [];
  if (!actions.length) return null;

  const primaryId = actions.find((a) => a.primary)?.id ?? actions[0]?.id;

  return (
    <View style={styles.row} testID="dynamic-actions">
      {actions.map((a, index) => {
        const tier = tierFor(a, index, primaryId);
        const navOnly =
          a.kind === 'maps' ||
          a.kind === 'navigate' ||
          a.kind === 'open' ||
          a.kind === 'guide' ||
          a.kind === 'study' ||
          a.kind === 'resume' ||
          a.kind === 'confirm' ||
          isGuidedAction(a);
        const loading = busy === a.id || busy === a.kind;

        return (
          <Pressable
            key={a.id}
            testID={`home-action-${a.id}`}
            accessibilityRole="button"
            accessibilityLabel={a.label}
            disabled={!!loading}
            onPress={async () => {
              if (navOnly) await navigateHomeAction(router, a, item);
              await onAction(a);
            }}
            style={({ pressed }) => [
              styles.base,
              tier === 'primary' && {
                backgroundColor: colors.accent,
                borderColor: colors.accent,
              },
              tier === 'secondary' && {
                backgroundColor: 'transparent',
                borderColor: colors.border,
              },
              tier === 'tertiary' && {
                backgroundColor: 'transparent',
                borderColor: 'transparent',
                paddingHorizontal: 8,
              },
              { opacity: loading ? 0.55 : pressed ? 0.82 : 1 },
            ]}
          >
            {loading ? (
              <ActivityIndicator
                size="small"
                color={tier === 'primary' ? colors.onAccent : colors.textSecondary}
              />
            ) : (
              <Text
                style={[
                  styles.label,
                  tier === 'primary' && { color: colors.onAccent, fontWeight: '600' },
                  tier === 'secondary' && { color: colors.textPrimary, fontWeight: '500' },
                  tier === 'tertiary' && {
                    color: colors.textTertiary,
                    fontWeight: '400',
                    fontSize: tokens.typography.caption.fontSize,
                  },
                ]}
              >
                {a.label}
              </Text>
            )}
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: tokens.spacing.sm,
  },
  base: {
    minHeight: tokens.touch.min,
    paddingHorizontal: 18,
    paddingVertical: 10,
    borderRadius: tokens.radius.full,
    borderWidth: StyleSheet.hairlineWidth,
    justifyContent: 'center',
    alignItems: 'center',
  },
  label: {
    fontSize: tokens.typography.button.fontSize,
    letterSpacing: tokens.typography.button.letterSpacing,
  },
});
