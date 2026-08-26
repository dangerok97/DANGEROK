import { useEffect, useRef } from 'react';
import { Animated, Easing, type ViewStyle } from 'react-native';

import { useReducedMotion } from './useReducedMotion';
import { QUIET_EASING, QUIET_MOTION } from './motionTokens';

export { QUIET_MOTION } from './motionTokens';

/**
 * The motion language, applied.
 *
 * `motionTokens` holds the three bands; this turns them into something a
 * component can use, and answers reduce-motion by returning zero — which every
 * consumer treats as "already there" rather than as a faster animation.
 * Reanimated's own layout animations read the same system preference, so the
 * two agree.
 */
const EASING = Easing.bezier(QUIET_EASING.x1, QUIET_EASING.y1, QUIET_EASING.x2, QUIET_EASING.y2);

export function useQuietMotion() {
  const reduced = useReducedMotion();
  return {
    reduced,
    micro: reduced ? 0 : QUIET_MOTION.micro,
    standard: reduced ? 0 : QUIET_MOTION.standard,
    surface: reduced ? 0 : QUIET_MOTION.surface,
  };
}

/**
 * Content arriving where a skeleton was.
 *
 * Opacity only, and deliberately so: the skeleton is already standing in the
 * real content's place, so anything that moved would be describing a
 * displacement that did not happen. `key` restarts it when the thing being
 * shown is genuinely a different thing.
 *
 * Under reduce-motion the fade is skipped entirely — the content is simply
 * there, which is the same information without the movement.
 */
export function Appear({
  children,
  style,
  delay = 0,
  testID,
}: {
  children: React.ReactNode;
  style?: ViewStyle | ViewStyle[];
  delay?: number;
  testID?: string;
}) {
  const { standard } = useQuietMotion();
  const opacity = useRef(new Animated.Value(standard === 0 ? 1 : 0)).current;

  useEffect(() => {
    if (standard === 0) {
      opacity.setValue(1);
      return;
    }
    const anim = Animated.timing(opacity, {
      toValue: 1,
      duration: standard,
      delay,
      easing: EASING,
      useNativeDriver: true,
    });
    anim.start();
    return () => anim.stop();
  }, [delay, opacity, standard]);

  return (
    <Animated.View style={[{ opacity }, style as any]} testID={testID}>
      {children}
    </Animated.View>
  );
}
