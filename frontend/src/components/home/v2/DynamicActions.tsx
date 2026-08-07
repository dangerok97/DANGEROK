import { View, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { HomeActionDef, HomeItem } from '@/src/api/client';
import { AppButton } from '@/src/components/ui/AppButton';
import { isGuidedAction, navigateHomeAction } from './homeNav';

type Props = {
  item: HomeItem;
  busy?: string | null;
  onAction: (action: HomeActionDef) => void | Promise<void>;
};

const ICON: Record<string, any> = {
  complete: 'checkmark',
  snooze: 'hourglass-outline',
  ignore: 'close',
  correct: 'swap-vertical',
  open: 'open-outline',
  guide: 'sparkles-outline',
  navigate: 'arrow-forward',
  maps: 'map-outline',
  pay: 'card-outline',
  study: 'book-outline',
  confirm: 'checkmark-circle-outline',
  resume: 'play',
};

/** Only type-specific actions from API — guided actions go through ActionEngine. */
export function DynamicActions({ item, busy, onAction }: Props) {
  const router = useRouter();
  const actions = item.actions || [];
  if (!actions.length) return null;

  return (
    <View style={styles.row} testID="dynamic-actions">
      {actions.map((a, index) => {
        const navOnly =
          a.kind === 'maps' ||
          a.kind === 'navigate' ||
          a.kind === 'open' ||
          a.kind === 'guide' ||
          a.kind === 'study' ||
          a.kind === 'resume' ||
          a.kind === 'confirm' ||
          isGuidedAction(a);
        const isPrimary = !!a.primary || index === 0;
        const variant =
          a.kind === 'ignore' || a.kind === 'snooze'
            ? 'ghost'
            : isPrimary
              ? 'primary'
              : 'secondary';
        return (
          <AppButton
            key={a.id}
            variant={variant}
            label={a.label}
            icon={ICON[a.kind] || 'ellipse-outline'}
            loading={busy === a.id}
            testID={`home-action-${a.id}`}
            haptic={false}
            onPress={async () => {
              if (navOnly) {
                await navigateHomeAction(router, a, item);
              }
              await onAction(a);
            }}
          />
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
});
