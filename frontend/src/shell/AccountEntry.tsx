import { Pressable, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';

import { useAuth } from '@/src/contexts/AuthContext';
import { useBreakpoint } from '@/src/theme/responsive';
import { tokens } from '@/src/theme/tokens';
import { haptic } from '@/src/utils/haptic';

import { Avatar } from './RailAccount';

/**
 * The way to your own account, on a phone.
 *
 * The bottom bar used to carry a sixth slot for Profilo, which made the
 * account look like a sixth place to go — and the five destinations are the
 * product's whole cognitive map. On desktop the rail already answers "who am
 * I" at its foot, so this renders nothing there rather than asking twice.
 *
 * It sits in the header of each ambient surface for one reason: a person must
 * be able to reach their account from wherever they are, and a header is the
 * only position every ambient surface already shares. It is their picture, at
 * the tap floor, and it says what it is.
 */
export function AccountEntry({ testID = 'account-entry' }: { testID?: string }) {
  const { user } = useAuth();
  const router = useRouter();
  const bp = useBreakpoint();

  if (bp === 'desktop') return null;

  return (
    <Pressable
      onPress={() => {
        haptic('tap');
        router.push('/(tabs)/profilo' as any);
      }}
      style={({ pressed }) => [styles.btn, pressed && styles.pressed]}
      accessibilityRole="button"
      accessibilityLabel={
        user?.name ? `Profilo e account di ${user.name}` : 'Profilo e account'
      }
      testID={testID}
    >
      <Avatar name={user?.name} picture={user?.picture} size={32} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  btn: {
    width: tokens.touch.min,
    height: tokens.touch.min,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: -6,
  },
  pressed: { opacity: 0.7 },
});
