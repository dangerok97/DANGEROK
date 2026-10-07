import React from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

export type LegalSection = {
  title: string;
  paragraphs: string[];
  bullets?: string[];
};

export function PublicLegalPage({
  title,
  subtitle,
  updated,
  sections,
}: {
  title: string;
  subtitle: string;
  updated: string;
  sections: LegalSection[];
}) {
  const { colors } = useTheme();

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.backgroundPrimary }}
      contentContainerStyle={styles.outer}
      contentInsetAdjustmentBehavior="automatic"
    >
      <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
        <Text style={[styles.brand, { color: colors.accent }]}>ORA</Text>
        <Text accessibilityRole="header" style={[styles.title, { color: colors.textPrimary }]}>
          {title}
        </Text>
        <Text style={[styles.subtitle, { color: colors.textSecondary }]}>{subtitle}</Text>
        <Text style={[styles.updated, { color: colors.textTertiary }]}>Ultimo aggiornamento: {updated}</Text>

        {sections.map((section) => (
          <View key={section.title} style={styles.section}>
            <Text accessibilityRole="header" style={[styles.heading, { color: colors.textPrimary }]}>
              {section.title}
            </Text>
            {section.paragraphs.map((paragraph, index) => (
              <Text key={`${section.title}-p-${index}`} style={[styles.body, { color: colors.textSecondary }]}>
                {paragraph}
              </Text>
            ))}
            {(section.bullets || []).map((bullet, index) => (
              <View key={`${section.title}-b-${index}`} style={styles.bulletRow}>
                <Text style={[styles.bullet, { color: colors.accent }]}>•</Text>
                <Text style={[styles.body, styles.bulletText, { color: colors.textSecondary }]}>{bullet}</Text>
              </View>
            ))}
          </View>
        ))}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  outer: {
    width: '100%',
    alignItems: 'center',
    paddingHorizontal: tokens.spacing.lg,
    paddingVertical: tokens.spacing.xxl,
  },
  card: {
    width: '100%',
    maxWidth: 860,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.xl,
    padding: tokens.spacing.xxl,
    gap: tokens.spacing.md,
  },
  brand: {
    fontSize: 15,
    fontWeight: '800',
    letterSpacing: 4,
  },
  title: {
    fontSize: 34,
    lineHeight: 41,
    fontWeight: '760' as any,
    letterSpacing: -0.8,
  },
  subtitle: {
    fontSize: 16,
    lineHeight: 24,
    maxWidth: 720,
  },
  updated: {
    fontSize: 12,
    lineHeight: 18,
    marginTop: 2,
  },
  section: {
    marginTop: tokens.spacing.lg,
    gap: tokens.spacing.sm,
  },
  heading: {
    fontSize: 20,
    lineHeight: 27,
    fontWeight: '700',
  },
  body: {
    fontSize: 15,
    lineHeight: 23,
  },
  bulletRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: tokens.spacing.sm,
  },
  bullet: {
    fontSize: 17,
    lineHeight: 23,
    fontWeight: '800',
  },
  bulletText: {
    flex: 1,
  },
});
