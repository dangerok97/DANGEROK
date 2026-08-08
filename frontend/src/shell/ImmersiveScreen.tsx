/**
 * Immersive foundation — full-attention wrapper.
 * Does not redesign Life Setup / conversation; only declares shell mode.
 */
import React from 'react';
import { StyleSheet, View, ViewProps } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTheme } from '@/src/theme/ThemeProvider';
import { useDeclareShellMode } from './ShellModeContext';

type Props = ViewProps & {
  children: React.ReactNode;
  /** When false, child owns safe area (e.g. existing Life Setup). */
  safe?: boolean;
  testID?: string;
};

export function ImmersiveScreen({
  children,
  safe = true,
  style,
  testID = 'immersive-screen',
  ...rest
}: Props) {
  useDeclareShellMode('immersive');
  const { colors } = useTheme();

  if (!safe) {
    return (
      <View
        style={[styles.fill, { backgroundColor: colors.backgroundPrimary }, style]}
        testID={testID}
        {...rest}
      >
        {children}
      </View>
    );
  }

  return (
    <SafeAreaView
      edges={['top', 'left', 'right', 'bottom']}
      style={[styles.fill, { backgroundColor: colors.backgroundPrimary }, style]}
      testID={testID}
      {...rest}
    >
      {children}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
});
