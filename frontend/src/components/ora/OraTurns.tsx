import * as React from 'react';
import { Linking, Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import { RichOraText } from '@/src/components/ora-ai/RichOraText';
import { useTheme } from '@/src/theme/ThemeProvider';
import { OraJourney, type OraJourneyView } from './OraJourney';
import { tokens } from '@/src/theme/tokens';
import { buildGoalWorkspaceHref } from '@/src/ora/oraNav';

export type OraSource = { title?: string; url?: string };

export type Turn = {
  role: 'user' | 'ora';
  text: string;
  messageId?: string;
  sources?: OraSource[];
  navigation?: OraNavigationOption[];
  uiActions?: OraUiAction[];
  /** Come arrivarci, confrontato: il modulo della reference. */
  journey?: OraJourneyView;
  attachments?: Array<{ name?: string }>;
  /** The send failed after the turn was already on screen. */
  failed?: boolean;
};

/* -------------------------------------------------------------------------- */

/**
 * What the user said: a small surface, right-aligned, deliberately narrower
 * than the column. It reads as an aside — the thing you said on the way to the
 * answer — rather than as one half of a ping-pong.
 */
function UserTurn({ turn, onRetry, cockpit = false }: { turn: Turn; onRetry?: () => void; cockpit?: boolean }) {
  const { colors } = useTheme();
  return (
    <View style={[styles.userRow, cockpit && styles.userRowCockpit]}>
      <View style={styles.userCol}>
        <View
          style={[
            styles.userBubble,
            cockpit && styles.userBubbleCockpit,
            { backgroundColor: cockpit ? 'rgba(24,43,60,.72)' : colors.surfaceWarm, borderColor: cockpit ? 'rgba(120,190,220,.22)' : colors.divider },
            turn.failed && { borderColor: colors.error },
          ]}
        >
          <Text style={[styles.userText, { color: colors.textPrimary }]}>{turn.text}</Text>
        </View>

        {turn.attachments?.length ? (
          <View style={styles.attachRow} testID="ora-turn-attachments">
            {turn.attachments
              .map((a) => a?.name)
              .filter(Boolean)
              .map((name, i) => (
                <View
                  key={`${name}-${i}`}
                  style={[styles.attachChip, { borderColor: colors.border }]}
                >
                  <Ionicons name="document-outline" size={13} color={colors.textTertiary} />
                  <Text
                    style={[styles.attachText, { color: colors.textSecondary }]}
                    numberOfLines={1}
                  >
                    {name}
                  </Text>
                </View>
              ))}
          </View>
        ) : null}

        {turn.failed ? (
          <View style={styles.failedRow}>
            <Text style={[styles.failedText, { color: colors.error }]}>Non inviato</Text>
            {onRetry ? (
              <Pressable
                onPress={onRetry}
                hitSlop={10}
                accessibilityRole="button"
                style={({ pressed }) => [styles.failedRetry, pressed && styles.pressed]}
                testID="ora-turn-retry"
              >
                <Text style={[styles.failedRetryLabel, { color: colors.textPrimary }]}>
                  Riprova
                </Text>
              </Pressable>
            ) : null}
          </View>
        ) : null}
      </View>
    </View>
  );
}

/**
 * What ORA said: open editorial text, left-aligned, full column width.
 *
 * No bubble, no avatar on every turn. A bubble frames a remark; ORA is not
 * making remarks, it is doing the thinking out loud, and long reasoning inside
 * a chat balloon becomes unreadable at exactly the moment it matters most.
 */
function OraTurnView({
  turn,
  showMark,
  cockpit = false,
}: {
  turn: Turn;
  showMark: boolean;
  cockpit?: boolean;
}) {
  const { colors } = useTheme();
  return (
    <View style={[styles.oraTurn, cockpit && styles.oraTurnCockpit]}>
      {showMark ? (
        cockpit ? (
          <View style={styles.oraIdentity}>
            <View style={styles.oraOrbOuter}>
              <View style={styles.oraOrbInner} />
            </View>
            <Text style={styles.oraMarkCockpit}>ORA</Text>
          </View>
        ) : (
          <Text style={[styles.oraMark, { color: colors.textTertiary }]}>ORA</Text>
        )
      ) : null}
      <RichOraText
        text={turn.text}
        color={colors.textPrimary}
        secondaryColor={colors.textSecondary}
        linkColor={colors.accent}
        dangerColor={cockpit ? '#ff7373' : colors.error}
      />
      <OraActions actions={turn.uiActions} />
      {turn.journey?.options?.length ? (
        <OraJourney journey={turn.journey} navigation={turn.navigation as any} />
      ) : (
        <>
          <OraNavigation options={turn.navigation} />
          {turn.journey?.unavailable ? <OraJourney journey={turn.journey} /> : null}
        </>
      )}
      <OraSources sources={turn.sources} />
    </View>
  );
}

export type OraNavigationOption = { id?: string; label?: string; url?: string };
export type OraUiAction = {
  kind: 'amazon_search' | 'workspace';
  label: string;
  url?: string;
  plan_id?: string;
};

/** A bounded interface assembled from verified destinations in this answer. */
export function OraActions({ actions }: { actions?: OraUiAction[] }) {
  const { colors } = useTheme();
  const router = useRouter();
  const valid = (actions || []).filter((a) => {
    if (a.kind === 'workspace') return /^lop_[A-Za-z0-9_-]{4,76}$/.test(a.plan_id || '');
    if (a.kind === 'amazon_search') {
      try {
        const u = new URL(a.url || '');
        return u.protocol === 'https:' && u.hostname === 'www.amazon.it' &&
          u.pathname === '/s' && Boolean(u.searchParams.get('k'));
      } catch { return false; }
    }
    return false;
  }).slice(0, 2);
  if (!valid.length) return null;
  return (
    <View style={styles.navigation} testID="ora-actions">
      {valid.map((a) => (
        <Pressable
          key={`${a.kind}-${a.url || a.plan_id}`}
          onPress={() => a.kind === 'workspace'
            ? router.push(buildGoalWorkspaceHref(a.plan_id || '') as any)
            : void Linking.openURL(a.url || '')}
          style={({ pressed }) => [styles.navButton, {
            borderColor: colors.border, backgroundColor: colors.surface,
            opacity: pressed ? 0.7 : 1,
          }]}
          accessibilityRole={a.kind === 'workspace' ? 'button' : 'link'}
          accessibilityLabel={a.label}
          testID={`ora-action-${a.kind}`}
        >
          <Ionicons name={a.kind === 'workspace' ? 'layers-outline' : 'open-outline'} size={14} color={colors.accent} />
          <Text style={[styles.navButtonText, { color: colors.textPrimary }]}>{a.label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

/**
 * The map apps ORA just offered, as buttons that open them.
 *
 * ORA works out *where*; the app the person already trusts does the driving.
 * Which apps appear is decided on the server by what the platform can actually
 * open — Apple Maps is not offered on Android — so this renders exactly what
 * it was given and never invents an option.
 */
export function OraNavigation({ options }: { options?: OraNavigationOption[] }) {
  const { colors } = useTheme();
  const rows = (options || [])
    .map((o) => {
      const url = String(o?.url || '').trim();
      const label = String(o?.label || '').trim();
      // A button with no link is a button that does nothing.
      return url && label && /^https?:\/\//i.test(url) ? { label, url } : null;
    })
    .filter(Boolean) as Array<{ label: string; url: string }>;

  if (!rows.length) return null;

  return (
    <View style={styles.navigation} testID="ora-navigation">
      {rows.map((r) => (
        <Pressable
          key={r.url}
          onPress={() => void Linking.openURL(r.url)}
          style={[styles.navButton, { borderColor: colors.border, backgroundColor: colors.surface }]}
          testID={`ora-navigate-${r.label.toLowerCase().replace(/\s+/g, '-')}`}
          accessibilityRole="link"
          accessibilityLabel={`Avvia navigazione con ${r.label}`}
        >
          <Ionicons name="navigate-outline" size={14} color={colors.accent} />
          <Text style={[styles.navButtonText, { color: colors.textPrimary }]}>{r.label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

/**
 * Where the answer came from.
 *
 * Only what the backend actually sent: a name, and a host when the URL is a
 * real one. No invented authority, and never the raw URL — a line of query
 * string is not information a person can use.
 */
export function OraSources({ sources }: { sources?: OraSource[] }) {
  const { colors } = useTheme();
  const rows = (sources || [])
    .map((s) => {
      const url = String(s?.url || '').trim();
      const safe = /^https?:\/\//i.test(url) ? url : null;
      let host: string | null = null;
      if (safe) {
        try {
          host = new URL(safe).hostname.replace(/^www\./, '');
        } catch {
          host = null;
        }
      }
      const name = String(s?.title || '').trim() || host;
      return name ? { name, host, url: safe } : null;
    })
    .filter(Boolean) as Array<{ name: string; host: string | null; url: string | null }>;

  if (!rows.length) return null;

  return (
    <View
      style={[styles.sources, { backgroundColor: colors.surface, borderColor: colors.border }]}
      testID="ora-sources"
    >
      <Text style={[styles.sourcesLabel, { color: colors.textTertiary }]}>FONTI</Text>
      {rows.map((r, i) => {
        const body = (
          <>
            <Text
              style={[
                styles.sourceName,
                { color: r.url ? colors.accent : colors.textPrimary },
              ]}
              numberOfLines={2}
            >
              {r.name}
            </Text>
            {r.host ? (
              <Text style={[styles.sourceHost, { color: colors.textTertiary }]} numberOfLines={1}>
                {r.host}
              </Text>
            ) : null}
          </>
        );
        if (!r.url) {
          return (
            <View key={`${r.name}-${i}`} style={styles.sourceRow}>
              {body}
            </View>
          );
        }
        return (
          <Pressable
            key={`${r.url}-${i}`}
            onPress={() => void Linking.openURL(r.url as string)}
            style={({ pressed }) => [styles.sourceRow, pressed && styles.pressed]}
            accessibilityRole="link"
            accessibilityLabel={`${r.name}${r.host ? `, ${r.host}` : ''}`}
            testID={`ora-source-${i}`}
          >
            {body}
          </Pressable>
        );
      })}
    </View>
  );
}

/** The conversation, as a sequence of two different kinds of thing. */
export function OraTurns({
  turns,
  onRetry,
  variant = 'default',
}: {
  turns: Turn[];
  onRetry?: (turn: Turn) => void;
  variant?: 'default' | 'cockpit';
}) {
  const cockpit = variant === 'cockpit';
  return (
    <>
      {turns.map((t, i) =>
        t.role === 'user' ? (
          <UserTurn
            key={t.messageId || `u-${i}-${t.text.slice(0, 24)}`}
            turn={t}
            cockpit={cockpit}
            onRetry={t.failed && onRetry ? () => onRetry(t) : undefined}
          />
        ) : (
          <OraTurnView
            key={t.messageId || `o-${i}-${t.text.slice(0, 24)}`}
            turn={t}
            showMark={turns[i - 1]?.role !== 'ora'}
            cockpit={cockpit}
          />
        ),
      )}
    </>
  );
}

const styles = StyleSheet.create({
  userRow: { flexDirection: 'row', justifyContent: 'flex-end', marginTop: tokens.spacing.xl },
  userRowCockpit: { marginTop: tokens.spacing.md },
  userCol: { maxWidth: '82%', alignItems: 'flex-end', gap: 6 },
  userBubble: {
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: tokens.spacing.lg,
    paddingVertical: tokens.spacing.md,
  },
  userBubbleCockpit: {
    borderRadius: 16,
    shadowColor: '#78dfff',
    shadowOpacity: 0.08,
    shadowRadius: 12,
  },
  userText: { fontSize: 15, lineHeight: 22 },
  attachRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, justifyContent: 'flex-end' },
  attachChip: {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    borderWidth: StyleSheet.hairlineWidth, borderRadius: tokens.radius.sm,
    paddingHorizontal: 8, paddingVertical: 5, maxWidth: 240,
  },
  attachText: { fontSize: 12, flexShrink: 1 },
  failedRow: { flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.md },
  failedText: { fontSize: 12 },
  failedRetry: { minHeight: 28, justifyContent: 'center' },
  failedRetryLabel: { fontSize: 12, fontWeight: '600', textDecorationLine: 'underline' },

  oraTurn: { marginTop: tokens.spacing.xl, gap: tokens.spacing.sm },
  oraTurnCockpit: {
    marginTop: tokens.spacing.lg,
    paddingHorizontal: 2,
  },
  oraMark: { fontSize: 11, fontWeight: '700', letterSpacing: 1.3 },
  oraIdentity: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
    marginBottom: 3,
  },
  oraOrbOuter: {
    width: 24,
    height: 24,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: 'rgba(137,225,255,.55)',
    backgroundColor: 'rgba(56,146,190,.08)',
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#7fe0ff',
    shadowOpacity: 0.75,
    shadowRadius: 10,
  },
  oraOrbInner: {
    width: 10,
    height: 10,
    borderRadius: 5,
    borderWidth: 2,
    borderColor: '#b9f0ff',
    backgroundColor: 'rgba(128,226,255,.20)',
  },
  oraMarkCockpit: {
    color: '#a9e6f4',
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 1.5,
  },

  navigation: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: tokens.spacing.sm,
    marginTop: tokens.spacing.md,
  },
  navButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.md,
    paddingHorizontal: tokens.spacing.md,
    paddingVertical: 9,
    minHeight: 40,
  },
  navButtonText: { fontSize: 13, fontWeight: '500' },
  sources: {
    marginTop: tokens.spacing.md,
    borderRadius: tokens.radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: tokens.spacing.lg,
    paddingVertical: tokens.spacing.md,
    gap: 2,
  },
  sourcesLabel: { fontSize: 10, fontWeight: '700', letterSpacing: 1.2, marginBottom: 4 },
  sourceRow: { paddingVertical: 7, minHeight: tokens.touch.min, justifyContent: 'center', gap: 1 },
  sourceName: { fontSize: 13, lineHeight: 18 },
  sourceHost: { fontSize: 11 },
  pressed: { opacity: 0.7 },
});
