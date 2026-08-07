import React from 'react';
import { StyleSheet, View, ViewProps } from 'react-native';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { GlassContainer } from './GlassContainer';

type Props = ViewProps & {
  children: React.ReactNode;
  glass?: boolean;
};

/** Bottom sheet chrome — glass optional; handle + elevated surface by default. */
export function BottomSheetContainer({ children, glass = true, style, ...rest }: Props) {
  const { colors, shadow } = useTheme();
  const body = (
    <>
      <View style={[styles.handle, { backgroundColor: colors.borderStrong }]} />
      {children}
    </>
  );

  if (glass) {
    return (
      <GlassContainer glassRole="sheet" style={[styles.sheet, style as object]} {...rest}>
        <View style={styles.pad}>{body}</View>
      </GlassContainer>
    );
  }

  return (
    <View
      style={[
        styles.sheet,
        styles.pad,
        {
          backgroundColor: colors.surfaceElevated,
          borderColor: colors.border,
        },
        shadow('floating'),
        style,
      ]}
      {...rest}
    >
      {body}
    </View>
  );
}

const styles = StyleSheet.create({
  sheet: {
    borderTopLeftRadius: tokens.radius['2xl'],
    borderTopRightRadius: tokens.radius['2xl'],
    overflow: 'hidden',
  },
  pad: {
    paddingTop: tokens.spacing.sm,
    paddingHorizontal: tokens.spacing.lg,
    paddingBottom: tokens.spacing.xl,
  },
  handle: {
    alignSelf: 'center',
    width: 36,
    height: 4,
    borderRadius: tokens.radius.full,
    marginBottom: tokens.spacing.md,
  },
});
