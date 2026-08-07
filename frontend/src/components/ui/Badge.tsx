import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

type Tone = 'neutral' | 'accent' | 'success' | 'warning' | 'error' | 'info';

type Props = {
  label: string;
  tone?: Tone;
};

export function Badge({ label, tone = 'neutral' }: Props) {
  const { colors } = useTheme();
  const map: Record<Tone, { bg: string; fg: string }> = {
    neutral: { bg: colors.backgroundSecondary, fg: colors.textSecondary },
    accent: { bg: colors.accentMuted, fg: colors.accent },
    success: { bg: colors.successBg, fg: colors.success },
    warning: { bg: colors.warningBg, fg: colors.warning },
    error: { bg: colors.errorBg, fg: colors.error },
    info: { bg: colors.infoBg, fg: colors.info },
  };
  const t = map[tone];
  return (
    <View style={[styles.badge, { backgroundColor: t.bg }]} accessibilityLabel={label}>
      <Text style={[styles.text, { color: t.fg }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    alignSelf: 'flex-start',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: tokens.radius.full,
  },
  text: {
    fontSize: tokens.typography.footnote.fontSize,
    fontWeight: '600',
  },
});
