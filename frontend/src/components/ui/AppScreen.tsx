import React from 'react';
import { ScrollView, StyleSheet, View, ViewProps, ViewStyle } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTheme } from '@/src/theme/ThemeProvider';
import { contentMaxWidth, useBreakpoint } from '@/src/theme/responsive';
import { tokens } from '@/src/theme/tokens';

type Props = ViewProps & {
  children: React.ReactNode;
  scroll?: boolean;
  padded?: boolean;
  edges?: ('top' | 'right' | 'bottom' | 'left')[];
  contentStyle?: ViewStyle;
  testID?: string;
};

/**
 * AppScreen — Quiet Premium root screen shell.
 * Safe area + warm/deep background + optional editorial max-width on large screens.
 */
export function AppScreen({
  children,
  scroll,
  padded = true,
  edges = ['top', 'left', 'right'],
  style,
  contentStyle,
  testID,
  ...rest
}: Props) {
  const { colors } = useTheme();
  const bp = useBreakpoint();
  const maxW = contentMaxWidth[bp];

  const inner = (
    <View
      style={[
        styles.inner,
        padded && styles.padded,
        maxW ? { maxWidth: maxW, alignSelf: 'center', width: '100%' } : null,
        contentStyle,
      ]}
    >
      {children}
    </View>
  );

  return (
    <SafeAreaView
      edges={edges}
      style={[styles.root, { backgroundColor: colors.backgroundPrimary }, style]}
      testID={testID}
      {...rest}
    >
      {scroll ? (
        <ScrollView
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {inner}
        </ScrollView>
      ) : (
        inner
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  inner: { flexGrow: 1 },
  padded: { paddingHorizontal: tokens.spacing.lg },
  scrollContent: { flexGrow: 1, paddingBottom: tokens.spacing.xxl },
});
