import * as React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { ContextualCardVisual } from '@/src/components/home/v3/ContextualCardVisual';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import type { VitaArea, VitaSituation } from './vitaModel';

/* -------------------------------------------------------------------------- */
/* Section shell                                                              */
/* -------------------------------------------------------------------------- */

/** A titled band. Renders nothing when it has nothing to say. */
export function VitaSection({
  title,
  children,
  footer,
  testID,
}: {
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  testID?: string;
}) {
  const { colors } = useTheme();
  const present = React.Children.toArray(children).filter(Boolean);
  if (!present.length) return null;
  return (
    <View style={styles.section} testID={testID}>
      <Text style={[styles.sectionLabel, { color: colors.textTertiary }]}>{title}</Text>
      {children}
      {footer}
    </View>
  );
}

/* -------------------------------------------------------------------------- */
/* IN QUESTO PERIODO                                                          */
/* -------------------------------------------------------------------------- */

/**
 * What is live in this person's life right now.
 *
 * The picture is the entity's own — the same one Home shows for the same
 * situation — so the card is recognisable before it is read. Text sits on the
 * left with the illustration bleeding off the right edge, which keeps the card
 * scannable at a glance rather than making the image the subject.
 */
export function SituationCard({
  situation,
  onOpen,
}: {
  situation: VitaSituation;
  onOpen?: () => void;
}) {
  const { colors } = useTheme();
  const openable = !!situation.href && !!onOpen;

  return (
    <View
      style={[
        styles.situation,
        { backgroundColor: colors.surfaceWarm, borderColor: colors.divider },
      ]}
      testID={`vita-situation-${situation.id}`}
    >
      <View style={styles.situationBody}>
        {/* Title runs the width of the card; only the lower half is shared
            with the illustration, which is where the reference puts it. */}
        <Text
          style={[styles.situationTitle, { color: colors.textPrimary }]}
          numberOfLines={2}
        >
          {situation.title}
        </Text>
        {situation.summary ? (
          <Text
            style={[styles.situationSummary, { color: colors.textSecondary }]}
            numberOfLines={2}
          >
            {situation.summary}
          </Text>
        ) : null}
        {situation.temporal ? (
          <View style={[styles.chip, { backgroundColor: colors.accentMuted }]}>
            <Text style={[styles.chipLabel, { color: colors.accent }]} numberOfLines={1}>
              {situation.temporal}
            </Text>
          </View>
        ) : null}
        {openable ? (
          <Pressable
            onPress={onOpen}
            style={({ pressed }) => [
              styles.openBtn,
              { backgroundColor: colors.accent },
              pressed && styles.pressed,
            ]}
            accessibilityRole="button"
            accessibilityLabel={`Apri ${situation.title}`}
            testID={`vita-open-${situation.id}`}
          >
            <Text style={[styles.openLabel, { color: colors.onAccent }]}>Apri</Text>
            <Ionicons name="arrow-forward" size={14} color={colors.onAccent} />
          </Pressable>
        ) : null}
      </View>

      <ContextualCardVisual
        imageSource={situation.visualUrl}
        generating={situation.visualPending}
        item={{ source_type: situation.kind }}
        size="card"
        style={styles.situationVisual}
        testID={`vita-visual-${situation.id}`}
      />
    </View>
  );
}

/* -------------------------------------------------------------------------- */
/* LA TUA VITA                                                                */
/* -------------------------------------------------------------------------- */

/**
 * One part of a life, summarised.
 *
 * A few sentences ORA would actually say, each with where it came from — not
 * the contents of a table. If ORA knows more, the card says so and the number
 * becomes the reason to open it, instead of the card growing until it becomes
 * the record it was supposed to summarise.
 */
export function LifeAreaCard({
  area,
  onOpen,
}: {
  area: VitaArea;
  onOpen: () => void;
}) {
  const { colors } = useTheme();
  return (
    <Pressable
      onPress={onOpen}
      style={({ pressed, hovered }: any) => [
        styles.area,
        {
          backgroundColor: hovered ? colors.surfaceElevated : colors.surface,
          borderColor: colors.border,
        },
        pressed && styles.pressed,
      ]}
      accessibilityRole="button"
      accessibilityLabel={`Apri ${area.title}`}
      testID={`vita-area-${area.domain}`}
    >
      <ContextualCardVisual
        imageSource={area.visualUrl}
        generating={area.visualPending}
        item={{ source_type: area.domain }}
        size="card"
        style={styles.areaVisual}
        testID={`vita-area-visual-${area.domain}`}
      />
      <View style={styles.areaBody}>
        <View style={styles.areaHead}>
          <Text style={[styles.areaTitle, { color: colors.textPrimary }]} numberOfLines={1}>
            {area.title}
          </Text>
          <Ionicons name="chevron-forward" size={16} color={colors.textTertiary} />
        </View>
        {area.identity ? (
          <Text style={[styles.areaIdentity, { color: colors.textSecondary }]} numberOfLines={1}>
            {area.identity}
          </Text>
        ) : null}
        {area.facts.length ? (
          <View style={styles.factList}>
            {area.facts.map((f) => (
              <View key={f.id} style={styles.factRow}>
                <Text style={[styles.factBullet, { color: colors.textTertiary }]}>·</Text>
                <Text
                  style={[styles.factText, { color: colors.textSecondary }]}
                  numberOfLines={2}
                >
                  {f.statement}
                </Text>
              </View>
            ))}
          </View>
        ) : null}
        {area.moreCount > 0 ? (
          <Text style={[styles.areaMore, { color: colors.textTertiary }]}>
            {area.moreCount === 1 ? 'e un’altra cosa' : `e altre ${area.moreCount} cose`}
          </Text>
        ) : null}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  section: { gap: tokens.spacing.md },
  sectionLabel: { fontSize: 11, fontWeight: '700', letterSpacing: 1.2 },

  situation: {
    flex: 1,
    minHeight: 236,
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    overflow: 'hidden',
    flexDirection: 'row',
  },
  situationBody: {
    flex: 1,
    padding: tokens.spacing.lg,
    gap: 6,
    zIndex: 1,
  },
  situationTitle: { fontSize: 17, fontWeight: '650' as any, lineHeight: 23, letterSpacing: -0.2 },
  /** Stops short of the illustration below-right; the title does not have to. */
  situationSummary: { fontSize: 13, lineHeight: 18, width: '62%' },
  chip: {
    alignSelf: 'flex-start',
    borderRadius: tokens.radius.sm,
    paddingHorizontal: 8,
    paddingVertical: 3,
    marginTop: 2,
    maxWidth: '100%',
  },
  chipLabel: { fontSize: 11, fontWeight: '600' },
  openBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start',
    minHeight: 36, paddingHorizontal: tokens.spacing.lg,
    borderRadius: tokens.radius.md, marginTop: 'auto',
  },
  openLabel: { fontSize: 13, fontWeight: '600' },
  /**
   * A panel down the right edge, full height and flush to the card's corners.
   * The first pass offset a square off the bottom-right corner, which cropped
   * the illustration at an angle and read as a sticker rather than as part of
   * the card.
   */
  /**
   * Seated in the bottom-right corner, flush to the card's edges and rounded
   * only where it meets the text. A full-height panel down the side left the
   * title barely two words wide in a three-across row; the picture belongs
   * under the words, not beside them.
   */
  situationVisual: {
    position: 'absolute',
    right: 0,
    bottom: 0,
    width: '52%',
    height: '58%',
    borderRadius: 0,
    borderTopLeftRadius: tokens.radius.lg,
  },

  area: {
    flex: 1,
    flexDirection: 'row',
    gap: tokens.spacing.md,
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    padding: tokens.spacing.md,
    minHeight: 140,
  },
  areaVisual: { width: 92, height: 92, alignSelf: 'flex-start' },
  areaBody: { flex: 1, gap: 3 },
  areaHead: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  areaTitle: { fontSize: 15, fontWeight: '650' as any, flex: 1, letterSpacing: -0.1 },
  areaIdentity: { fontSize: 12, lineHeight: 17, marginBottom: 2 },
  factList: { gap: 2 },
  factRow: { flexDirection: 'row', gap: 6, alignItems: 'flex-start' },
  factBullet: { fontSize: 12, lineHeight: 17 },
  factText: { fontSize: 12, lineHeight: 17, flex: 1 },
  areaMore: { fontSize: 11, marginTop: 2 },
  pressed: { opacity: 0.75 },
});
