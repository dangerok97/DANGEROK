import React, { useEffect, useRef } from 'react';
import { Animated, StyleSheet, View, ViewStyle } from 'react-native';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

type Props = {
  width?: number | `${number}%`;
  height?: number;
  radius?: number;
  style?: ViewStyle;
};

export function LoadingSkeleton({
  width = '100%',
  height = 16,
  radius = tokens.radius.sm,
  style,
}: Props) {
  const { colors } = useTheme();
  const opacity = useRef(new Animated.Value(0.45)).current;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, {
          toValue: 1,
          duration: tokens.motion.slow,
          useNativeDriver: true,
        }),
        Animated.timing(opacity, {
          toValue: 0.45,
          duration: tokens.motion.slow,
          useNativeDriver: true,
        }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [opacity]);

  return (
    <Animated.View
      style={[
        {
          width,
          height,
          borderRadius: radius,
          backgroundColor: colors.skeleton,
          opacity,
        },
        style,
      ]}
      accessibilityRole="progressbar"
      accessibilityLabel="Caricamento"
    />
  );
}

export function SkeletonBlock({ lines = 3 }: { lines?: number }) {
  return (
    <View style={styles.block}>
      {Array.from({ length: lines }).map((_, i) => (
        <LoadingSkeleton key={i} width={i === lines - 1 ? '70%' : '100%'} height={14} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  block: { gap: tokens.spacing.sm },
});
