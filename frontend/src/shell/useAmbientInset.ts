import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useBreakpoint } from '@/src/theme/responsive';
import { AMBIENT_BOTTOM_CLEARANCE } from './constants';

/**
 * Padding so Ambient chrome does not cover content.
 * Desktop rail is a real layout sibling (fixed width) — do NOT add paddingLeft.
 * Phone/tablet: bottom clearance for the floating Ambient bar only.
 */
export function useAmbientInset(): {
  paddingBottom: number;
  paddingLeft: number;
  isRail: boolean;
} {
  const bp = useBreakpoint();
  const insets = useSafeAreaInsets();
  const isRail = bp === 'desktop';
  return {
    isRail,
    paddingLeft: 0,
    paddingBottom: isRail ? Math.max(insets.bottom, 24) : AMBIENT_BOTTOM_CLEARANCE + insets.bottom,
  };
}
