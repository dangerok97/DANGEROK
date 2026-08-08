/**
 * Focus mode screen shell — one task, no Ambient nav, editorial max-width.
 */
import React, { useEffect } from 'react';
import { StyleSheet, View, ViewProps, ViewStyle } from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTheme } from '@/src/theme/ThemeProvider';
import { contentMaxWidth, useBreakpoint } from '@/src/theme/responsive';
import { tokens } from '@/src/theme/tokens';
import { useDeclareShellMode } from './ShellModeContext';
import { FocusChrome } from './FocusChrome';
import { useShellTransitionMs } from './transitions';

type Props = ViewProps & {
  children: React.ReactNode;
  chrome?: React.ComponentProps<typeof FocusChrome>;
  contentStyle?: ViewStyle;
  /** Override editorial max-width (e.g. Action decision ~720). Shell default uses contentMaxWidth. */
  maxWidth?: number;
  testID?: string;
};

export function FocusScreen({
  children,
  chrome,
  style,
  contentStyle,
  maxWidth,
  testID = 'focus-screen',
  ...rest
}: Props) {
  useDeclareShellMode('focus');
  const { colors } = useTheme();
  const bp = useBreakpoint();
  const maxW = maxWidth ?? contentMaxWidth[bp] ?? 640;
  const duration = useShellTransitionMs();

  useEffect(() => {
    // Mode declaration side-effect only — Ambient bar must not mount here.
  }, []);

  const body = (
    <View
      style={[
        styles.canvas,
        { backgroundColor: colors.backgroundPrimary },
        style,
      ]}
      testID={testID}
      {...rest}
    >
      {chrome ? <FocusChrome {...chrome} /> : null}
      <View
        style={[
          styles.content,
          { maxWidth: maxW },
          contentStyle,
        ]}
      >
        {children}
      </View>
    </View>
  );

  return (
    <SafeAreaView
      edges={['top', 'left', 'right', 'bottom']}
      style={[styles.root, { backgroundColor: colors.backgroundPrimary }]}
    >
      {duration > 0 ? (
        <Animated.View entering={FadeIn.duration(duration)} style={styles.fill}>
          {body}
        </Animated.View>
      ) : (
        body
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  fill: { flex: 1 },
  canvas: { flex: 1 },
  content: {
    flex: 1,
    width: '100%',
    alignSelf: 'center',
    paddingHorizontal: tokens.spacing.xl,
  },
});
