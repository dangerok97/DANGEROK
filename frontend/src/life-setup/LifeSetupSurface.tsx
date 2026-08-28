/**
 * The surface the first conversation happens on.
 *
 * The conversation itself was already right; what was missing was everywhere
 * around it. A bare thread with a progress bar reads as a technical chat —
 * "answer the machine" — when the thing actually happening is ORA starting to
 * understand somebody's life. So the words stay in the middle, and around them
 * sits enough structure to say what this is: who is asking, what it is for,
 * what part of your life we are on, what else there is, and that you can leave
 * whenever you like.
 *
 * What it deliberately is *not* is a form. The current area shows what ORA
 * already knows and what would still help — as sentences, not fields — and the
 * other areas are a list you can look at, not a queue you must clear. Nothing
 * here can be typed into except the composer.
 */
import { ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View, useWindowDimensions } from 'react-native';

import { LifeAreaCompleteness } from '@/src/api/client';
import { LifeProfileProgress } from '@/src/components/life-profile/LifeProfileProgress';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

/** Wide enough for a calm second column, not so wide it needs one. */
const TWO_COLUMN_AT = 900;
const RAIL_WIDTH = 320;

export type LifeSetupSurfaceProps = {
  percent: number;
  areas: LifeAreaCompleteness[];
  currentAreaId?: string | null;
  /** True until the person has said anything at all. */
  atTheStart: boolean;
  onSkipArea?: () => void;
  onLeave?: () => void;
  children: ReactNode;
};

function Welcome() {
  const { colors } = useTheme();
  return (
    <View style={styles.welcome} testID="life-setup-welcome">
      <Text style={[styles.hello, { color: colors.textPrimary }]}>Benvenuto in ORA</Text>
      <Text style={[styles.promise, { color: colors.textSecondary }]}>
        ORA imparerà a conoscere la tua vita, un pezzo alla volta, per aiutarti
        davvero ogni giorno. Rispondi solo a quello che ti va: puoi saltare
        qualsiasi cosa e riprendere quando vuoi.
      </Text>
    </View>
  );
}

/**
 * The part of a life this conversation is on.
 *
 * Shows what ORA already understands here and what would still help — as
 * things, not questions. The questions are written one at a time, in the
 * thread, by the part of ORA that knows what was just said.
 */
function CurrentArea({
  area,
  onSkip,
}: {
  area: LifeAreaCompleteness;
  onSkip?: () => void;
}) {
  const { colors } = useTheme();
  const missing = area.open_objectives.slice(0, 3);
  return (
    <View
      style={[styles.card, { borderColor: colors.border, backgroundColor: colors.surface }]}
      testID="life-setup-current-area"
    >
      <View style={styles.cardHead}>
        <View style={styles.cardTitleWrap}>
          <Text style={[styles.cardTitle, { color: colors.textPrimary }]}>{area.title}</Text>
          <Text style={[styles.cardSub, { color: colors.textSecondary }]}>
            {area.description}
          </Text>
        </View>
        <Text style={[styles.cardPercent, { color: colors.textTertiary }]}>{area.percent}%</Text>
      </View>

      {area.known_count > 0 ? (
        <Text style={[styles.cardNote, { color: colors.textTertiary }]}>
          {area.known_count === 1
            ? 'ORA sa già una cosa di questa parte della tua vita.'
            : `ORA sa già ${area.known_count} cose di questa parte della tua vita.`}
        </Text>
      ) : null}

      {missing.length ? (
        <View style={styles.chips} testID="life-setup-area-objectives">
          {missing.map((o) => (
            <View
              key={o.ref}
              style={[styles.chip, { borderColor: colors.border }]}
              testID={`life-setup-objective-${o.ref}`}
            >
              <Text style={[styles.chipText, { color: colors.textSecondary }]} numberOfLines={1}>
                {o.label}
              </Text>
            </View>
          ))}
        </View>
      ) : null}

      {onSkip ? (
        <Pressable
          onPress={onSkip}
          accessibilityRole="button"
          accessibilityLabel={`Salta ${area.title}`}
          style={styles.cardAction}
          testID="life-setup-skip-area"
        >
          <Text style={[styles.link, { color: colors.accent }]}>Salta questa parte</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

function OtherAreas({ areas, currentAreaId }: { areas: LifeAreaCompleteness[]; currentAreaId?: string | null }) {
  const { colors } = useTheme();
  const rest = areas.filter((a) => a.area_id !== currentAreaId && a.state !== 'not_applicable');
  if (!rest.length) return null;
  return (
    <View style={styles.others} testID="life-setup-other-areas">
      <Text style={[styles.othersTitle, { color: colors.textTertiary }]}>
        Altre parti (puoi arrivarci quando vuoi)
      </Text>
      {rest.map((a) => (
        <View
          key={a.area_id}
          style={[styles.otherRow, { borderColor: colors.border }]}
          testID={`life-setup-other-${a.area_id}`}
        >
          <Text style={[styles.otherTitle, { color: colors.textPrimary }]} numberOfLines={1}>
            {a.title}
          </Text>
          <Text style={[styles.otherState, { color: colors.textTertiary }]} numberOfLines={1}>
            {a.state_label}
          </Text>
        </View>
      ))}
    </View>
  );
}

function PrivacyNote({ onLeave }: { onLeave?: () => void }) {
  const { colors } = useTheme();
  return (
    <View style={styles.footer} testID="life-setup-footer">
      <Text style={[styles.footerText, { color: colors.textTertiary }]}>
        I tuoi dati restano tuoi. Puoi correggerli o rimuoverli da Vita, in
        qualsiasi momento.
      </Text>
      {onLeave ? (
        <Pressable
          onPress={onLeave}
          accessibilityRole="button"
          style={styles.footerAction}
          testID="life-setup-leave"
        >
          <Text style={[styles.link, { color: colors.accent }]}>Salta per ora</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

export function LifeSetupSurface({
  percent,
  areas,
  currentAreaId,
  atTheStart,
  onSkipArea,
  onLeave,
  children,
}: LifeSetupSurfaceProps) {
  const { width } = useWindowDimensions();
  const twoColumn = width >= TWO_COLUMN_AT;
  const current = areas.find((a) => a.area_id === currentAreaId) || null;

  const aside = (
    <>
      <LifeProfileProgress percent={percent} areas={areas} activeAreaId={currentAreaId} compact />
      {twoColumn ? <OtherAreas areas={areas} currentAreaId={currentAreaId} /> : null}
      {twoColumn ? <PrivacyNote onLeave={onLeave} /> : null}
    </>
  );

  return (
    <View style={[styles.root, twoColumn && styles.rootWide]} testID="life-setup-surface">
      <View style={styles.main}>
        {atTheStart ? <Welcome /> : null}
        {!twoColumn ? (
          <LifeProfileProgress
            percent={percent}
            areas={areas}
            activeAreaId={currentAreaId}
            compact
          />
        ) : null}
        {current ? <CurrentArea area={current} onSkip={onSkipArea} /> : null}
        {children}
        {!twoColumn ? <OtherAreas areas={areas} currentAreaId={currentAreaId} /> : null}
        {!twoColumn ? <PrivacyNote onLeave={onLeave} /> : null}
      </View>
      {twoColumn ? <View style={[styles.rail, { width: RAIL_WIDTH }]}>{aside}</View> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  // Centred and bounded: a first conversation that stretches the full width of
  // a desktop reads as a console, and the line length stops being readable
  // long before that.
  root: { flex: 1, gap: tokens.spacing.lg, alignSelf: 'center', width: '100%', maxWidth: 1040 },
  rootWide: { flexDirection: 'row', alignItems: 'flex-start' },
  main: { flex: 1, gap: tokens.spacing.lg, maxWidth: 680 },
  rail: { gap: tokens.spacing.lg },

  welcome: { gap: 6 },
  hello: { fontSize: 26, fontWeight: '600', letterSpacing: -0.4 },
  promise: { fontSize: 14, lineHeight: 21, maxWidth: 560 },

  card: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.lg,
    padding: tokens.spacing.md,
    gap: tokens.spacing.sm,
  },
  cardHead: { flexDirection: 'row', alignItems: 'flex-start', gap: tokens.spacing.sm },
  cardTitleWrap: { flex: 1, gap: 2 },
  cardTitle: { fontSize: 17, fontWeight: '600' },
  cardSub: { fontSize: 13, lineHeight: 19 },
  cardPercent: { fontSize: 13, fontVariant: ['tabular-nums'] },
  cardNote: { fontSize: 12, lineHeight: 17 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  chip: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.pill,
    paddingHorizontal: 10,
    paddingVertical: 5,
    maxWidth: 240,
  },
  chipText: { fontSize: 12 },
  cardAction: { minHeight: 44, justifyContent: 'center' },

  others: { gap: 6 },
  othersTitle: { fontSize: 11, letterSpacing: 0.4, textTransform: 'uppercase' },
  otherRow: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: tokens.spacing.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.md,
    paddingHorizontal: tokens.spacing.md,
    paddingVertical: 10,
  },
  otherTitle: { fontSize: 14, flex: 1 },
  otherState: { fontSize: 12 },

  footer: { gap: 4 },
  footerText: { fontSize: 12, lineHeight: 17 },
  footerAction: { minHeight: 44, justifyContent: 'center' },
  link: { fontSize: 13, fontWeight: '500' },
});
