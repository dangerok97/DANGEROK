import * as React from 'react';
import { Linking, Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { RichOraText } from '@/src/components/ora-ai/RichOraText';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

export type OraSource = { title?: string; url?: string };

export type Turn = {
  role: 'user' | 'ora';
  text: string;
  messageId?: string;
  sources?: OraSource[];
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
function UserTurn({ turn, onRetry }: { turn: Turn; onRetry?: () => void }) {
  const { colors } = useTheme();
  return (
    <View style={styles.userRow}>
      <View style={styles.userCol}>
        <View
          style={[
            styles.userBubble,
            { backgroundColor: colors.surfaceWarm, borderColor: colors.divider },
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
}: {
  turn: Turn;
  showMark: boolean;
}) {
  const { colors } = useTheme();
  return (
    <View style={styles.oraTurn}>
      {/* The mark appears when ORA starts speaking after the user, not on
          every consecutive paragraph — repeating it is noise, not identity. */}
      {showMark ? (
        <Text style={[styles.oraMark, { color: colors.textTertiary }]}>ORA</Text>
      ) : null}
      <RichOraText
        text={turn.text}
        color={colors.textPrimary}
        secondaryColor={colors.textSecondary}
        linkColor={colors.accent}
      />
      <OraSources sources={turn.sources} />
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
}: {
  turns: Turn[];
  onRetry?: (turn: Turn) => void;
}) {
  return (
    <>
      {turns.map((t, i) =>
        t.role === 'user' ? (
          <UserTurn
            key={t.messageId || `u-${i}-${t.text.slice(0, 24)}`}
            turn={t}
            onRetry={t.failed && onRetry ? () => onRetry(t) : undefined}
          />
        ) : (
          <OraTurnView
            key={t.messageId || `o-${i}-${t.text.slice(0, 24)}`}
            turn={t}
            showMark={turns[i - 1]?.role !== 'ora'}
          />
        ),
      )}
    </>
  );
}

const styles = StyleSheet.create({
  userRow: { flexDirection: 'row', justifyContent: 'flex-end', marginTop: tokens.spacing.xl },
  userCol: { maxWidth: '82%', alignItems: 'flex-end', gap: 6 },
  userBubble: {
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: tokens.spacing.lg,
    paddingVertical: tokens.spacing.md,
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
  oraMark: { fontSize: 11, fontWeight: '700', letterSpacing: 1.3 },

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
