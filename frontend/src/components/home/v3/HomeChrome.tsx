import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { AccountEntry, titleCase } from '@/src/shell';

/** Morning / afternoon / evening — the only thing a greeting needs to know. */
export function greetingFor(now: Date = new Date()): string {
  const h = now.getHours();
  if (h < 5) return 'Buonanotte';
  if (h < 13) return 'Buongiorno';
  if (h < 18) return 'Buon pomeriggio';
  return 'Buonasera';
}

/**
 * Header — a greeting, and one line telling the user what this page is for.
 *
 * The name comes from the session that is already loaded; no request is made
 * to say hello. It stays one line high on purpose: a greeting that fills the
 * screen is a greeting that delays the thing the user came for.
 */
export function HomeHeaderV3({
  name,
  ambient,
  permission,
  permissionBusy,
  onEnableNotifications,
  onDismissNotifications,
  onWhyNow,
}: {
  name?: string | null;
  /**
   * One line about work ORA actually did, when there is one.
   *
   * It sits under the greeting rather than in a section of its own because
   * that is what it is: a note about the state of things, read on the way
   * past. Given a card and a heading it would start to look like an activity
   * feed, and an activity feed is a thing people scroll rather than a thing
   * that makes a product feel present.
   */
  ambient?: { text: string; at: string } | null;
  /**
   * The notification question, when something real is waiting on it.
   *
   * It lives here rather than in a section of its own because it is the same
   * kind of thing as the ambient line: a quiet note under the greeting that
   * can be read on the way past and ignored without consequence.
   */
  permission?: { reason: string; example?: string | null } | null;
  permissionBusy?: boolean;
  onEnableNotifications?: () => void;
  onDismissNotifications?: () => void;
  onWhyNow?: () => void;
}) {
  const { colors } = useTheme();
  const first = titleCase(name).split(/\s+/)[0] || null;

  return (
    <View style={styles.header} testID="home-header">
      <View style={styles.headerText}>
        {/*
          The one level-one heading on Home. Every `accessibilityRole="header"`
          without a level renders as <h1> on web, so the greeting, the hero and
          each section title were all announcing themselves as the page's
          title — five of them. The greeting is the page; the rest sit under it.
        */}
        <Text
          style={[styles.greeting, { color: colors.textPrimary }]}
          accessibilityRole="header"
          aria-level={1}
        >
          {greetingFor()}{first ? `, ${first}.` : '.'}
        </Text>
        <Text style={[styles.sub, { color: colors.textSecondary }]}>
          Ecco cosa conta davvero ora.
        </Text>
        <NotificationMoment
          prompt={permission}
          busy={permissionBusy}
          onEnable={() => onEnableNotifications?.()}
          onLater={() => onDismissNotifications?.()}
        />
        {ambient?.text ? (
          <Text
            style={[styles.ambient, { color: colors.textTertiary }]}
            testID="home-ambient"
            numberOfLines={2}
          >
            {ambient.text}
            {agoLabel(ambient.at) ? ` · ${agoLabel(ambient.at)}` : ''}
          </Text>
        ) : null}
      </View>
      {onWhyNow ? (
        <Pressable
          onPress={onWhyNow}
          style={({ pressed }) => [
            styles.whyBtn,
            { backgroundColor: colors.surface, borderColor: colors.border },
            pressed && styles.pressed,
          ]}
          accessibilityRole="button"
          testID="home-why-now"
        >
          <Ionicons name="sparkles-outline" size={14} color={colors.accent} />
          <Text style={[styles.whyLabel, { color: colors.textSecondary }]}>Perché ora?</Text>
        </Pressable>
      ) : null}
      {/*
        Account, where a phone can reach it. Renders nothing on desktop, where
        the rail already answers this at its foot.
      */}
      <AccountEntry testID="home-account" />
    </View>
  );
}

/**
 * Empty Home. Not an error, not a blank page — a calm statement that there is
 * genuinely nothing demanding attention, plus the one affordance that still
 * makes sense.
 */
export function HomeEmptyV3({ onAsk }: { onAsk?: () => void }) {
  const { colors } = useTheme();
  return (
    <View
      style={[styles.empty, { backgroundColor: colors.surface, borderColor: colors.border }]}
      testID="home-empty"
    >
      <View style={[styles.emptyMark, { backgroundColor: colors.accentMuted }]}>
        <Ionicons name="checkmark" size={22} color={colors.accent} />
      </View>
      <Text style={[styles.emptyTitle, { color: colors.textPrimary }]}>
        Per ora non c'è nulla che richieda la tua attenzione.
      </Text>
      <Text style={[styles.emptyBody, { color: colors.textSecondary }]}>
        ORA continua a seguire quello che cambia. Se serve qualcosa, lo troverai qui.
      </Text>
      {onAsk ? (
        <Pressable
          onPress={onAsk}
          style={({ pressed }) => [styles.emptyCta, { borderColor: colors.border }, pressed && styles.pressed]}
          accessibilityRole="button"
        >
          <Text style={[styles.emptyCtaLabel, { color: colors.textPrimary }]}>Chiedi a ORA</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

/**
 * Loading. Shaped like the page it precedes, so nothing jumps when the real
 * content lands — the hero block stays a hero block, the sections stay
 * sections.
 */
export function HomeSkeletonV3({ wide }: { wide: boolean }) {
  const { colors } = useTheme();
  const bar = (w: number | string, h = 12) => (
    <View style={{ width: w as number, height: h, borderRadius: 6, backgroundColor: colors.skeleton }} />
  );
  return (
    <View style={styles.skeleton} testID="home-skeleton">
      <View style={[styles.skHero, { backgroundColor: colors.surface, borderColor: colors.border }]}>
        <View style={styles.skHeroText}>
          {bar(60, 10)}
          {bar('70%' as unknown as number, 26)}
          {bar('50%' as unknown as number)}
          {bar(140, 40)}
        </View>
        {wide ? <View style={[styles.skHeroVisual, { backgroundColor: colors.skeleton }]} /> : null}
      </View>
      {[0, 1].map((i) => (
        <View key={i} style={[styles.skSection, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          {bar(110, 10)}
          {bar('90%' as unknown as number)}
          {bar('75%' as unknown as number)}
        </View>
      ))}
    </View>
  );
}

/**
 * The moment it is worth asking about notifications.
 *
 * It appears because something real is waiting on it — ORA judged a
 * particular thing worth reaching this person for and could not — and it
 * disappears the moment that stops being true. Nothing schedules it, nothing
 * repeats it, and saying no costs nothing: quiet presence and the cards on
 * this page carry on exactly as before.
 *
 * Deliberately a line and two words, not a card with an illustration. A
 * permission prompt dressed up as an announcement is asking for something
 * while pretending to offer it.
 */
export function NotificationMoment({
  prompt,
  busy,
  onEnable,
  onLater,
}: {
  prompt?: { reason: string; example?: string | null } | null;
  busy?: boolean;
  onEnable: () => void;
  onLater: () => void;
}) {
  const { colors } = useTheme();
  if (!prompt?.reason) return null;

  return (
    <View style={styles.permission} testID="notification-moment">
      <Text style={[styles.permissionText, { color: colors.textSecondary }]}>
        {prompt.reason}
      </Text>
      {prompt.example ? (
        <Text style={[styles.permissionExample, { color: colors.textTertiary }]} numberOfLines={2}>
          Adesso, per esempio: {lowerFirst(prompt.example)}
        </Text>
      ) : null}
      <View style={styles.permissionActions}>
        <Pressable
          onPress={onEnable}
          disabled={busy}
          style={({ pressed }) => [styles.permissionCta, pressed && styles.pressed]}
          accessibilityRole="button"
          testID="notification-enable"
        >
          <Text style={[styles.permissionCtaText, { color: colors.accent }]}>
            Attiva notifiche
          </Text>
        </Pressable>
        <Pressable
          onPress={onLater}
          style={({ pressed }) => [styles.permissionCta, pressed && styles.pressed]}
          accessibilityRole="button"
          testID="notification-later"
        >
          <Text style={[styles.permissionCtaText, { color: colors.textSecondary }]}>
            Non ora
          </Text>
        </Pressable>
      </View>
    </View>
  );
}

/* Una frase incollata a "per esempio" non inizia con la maiuscola. */
function lowerFirst(text: string): string {
  const t = (text || '').trim();
  if (!t) return t;
  return t.charAt(0).toLocaleLowerCase('it-IT') + t.slice(1);
}

/**
 * How long ago, roughly.
 *
 * Deliberately vague. "poco fa" is what a person would say, and a precise
 * timestamp on a line about background work invites the reader to audit it
 * rather than to glance at it.
 */
function agoLabel(iso?: string | null): string {
  if (!iso) return '';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const minutes = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (minutes < 10) return 'poco fa';
  if (minutes < 60) return `${minutes} min fa`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return hours === 1 ? "un'ora fa" : `${hours} ore fa`;
  return 'ieri';
}

const styles = StyleSheet.create({
  /*
    Three things now share this row on a phone: the title, the "why" pill and
    the account. At 390px they do not fit on one line, and without a floor the
    title column shrank until "Buongiorno" broke across two lines mid-word.
    The floor makes the row wrap instead — the title keeps the full width and
    the two controls move together to the line below, which is the same
    hierarchy, one line lower. Nothing changes above the phone breakpoint.
  */
  header: {
    flexDirection: 'row', alignItems: 'flex-start',
    gap: tokens.spacing.lg, flexWrap: 'wrap',
  },
  headerText: { flex: 1, gap: 4, minWidth: 240 },
  greeting: { fontSize: 30, fontWeight: '700', letterSpacing: -0.8, lineHeight: 37 },
  permission: {
    gap: 2,
    marginTop: 4,
  },
  permissionText: {
    fontSize: tokens.typography.bodySmall.fontSize,
    lineHeight: tokens.typography.bodySmall.lineHeight,
  },
  permissionExample: {
    fontSize: tokens.typography.footnote.fontSize,
    lineHeight: 17,
  },
  permissionActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
    marginTop: 2,
  },
  permissionCta: {
    minHeight: tokens.touch.min,
    justifyContent: 'center',
  },
  permissionCtaText: { fontSize: 13, fontWeight: '600' },
  ambient: {
    fontSize: tokens.typography.footnote.fontSize,
    lineHeight: 18,
    marginTop: 6,
  },
  sub: { fontSize: 15, lineHeight: 21 },
  whyBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.md,
    paddingHorizontal: tokens.spacing.lg,
    minHeight: tokens.touch.min,
  },
  whyLabel: { fontSize: 13, fontWeight: '500' },
  empty: {
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    padding: tokens.spacing.xxl,
    alignItems: 'center',
    gap: tokens.spacing.sm,
  },
  emptyMark: {
    width: 46, height: 46, borderRadius: 23,
    alignItems: 'center', justifyContent: 'center',
    marginBottom: 4,
  },
  emptyTitle: { fontSize: 17, fontWeight: '600', textAlign: 'center', lineHeight: 24 },
  emptyBody: { fontSize: 14, textAlign: 'center', lineHeight: 20, maxWidth: 360 },
  emptyCta: {
    marginTop: tokens.spacing.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.md,
    paddingHorizontal: tokens.spacing.xl,
    minHeight: tokens.touch.min,
    justifyContent: 'center',
  },
  emptyCtaLabel: { fontSize: 14, fontWeight: '600' },
  skeleton: { gap: tokens.spacing.lg },
  skHero: {
    flexDirection: 'row',
    borderRadius: tokens.radius.xl,
    borderWidth: StyleSheet.hairlineWidth,
    overflow: 'hidden',
    minHeight: 210,
  },
  skHeroText: { flex: 1, padding: tokens.spacing.xl, gap: tokens.spacing.md },
  skHeroVisual: { width: 260 },
  skSection: {
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    padding: tokens.spacing.lg,
    gap: tokens.spacing.md,
  },
  pressed: { opacity: 0.7 },
});
