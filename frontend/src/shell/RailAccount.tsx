import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Image } from 'expo-image';
import { Ionicons } from '@expo/vector-icons';

import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { mediaHeaders, mediaUrl } from '@/src/api/client';

/**
 * Presentation casing only — the stored name is never rewritten.
 *
 * People type their own name in lower case all the time; addressing them as
 * "francesco" reads like a database row, not like being greeted. Capitalising
 * for display costs nothing and is reversible, whereas normalising what is
 * saved would quietly overwrite how someone chose to write their own name.
 */
export function titleCase(value?: string | null): string {
  return (value || '')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toLocaleUpperCase('it-IT') + w.slice(1))
    .join(' ');
}

/**
 * The person, at the foot of the rail.
 *
 * Not a "Profilo" menu entry — their face and their name. It is the one place
 * in the product that answers "who am I inside ORA", and it costs nothing to
 * answer it properly: the name and picture are already in the loaded session,
 * so this makes no request of its own.
 *
 * The picture is the user's, never generated and never invented. Without one,
 * the fallback is their initials on a quiet accent field — recognisably them,
 * rather than a stock silhouette pretending to be a photo.
 */
export function RailAccount({
  name,
  email,
  picture,
  selected,
  onPress,
}: {
  name?: string | null;
  email?: string | null;
  picture?: string | null;
  selected?: boolean;
  onPress: () => void;
}) {
  const { colors } = useTheme();
  const display = titleCase((name || '').trim() || (email || '').split('@')[0]) || 'Account';
  const first = display.split(/\s+/)[0];

  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected: !!selected }}
      accessibilityLabel={`Profilo e account di ${display}`}
      testID="rail-account"
      style={({ pressed }) => [
        styles.row,
        selected && { backgroundColor: colors.accentMuted },
        pressed && styles.pressed,
      ]}
    >
      <Avatar name={display} picture={picture} size={32} />
      <Text style={[styles.name, { color: colors.textPrimary }]} numberOfLines={1}>
        {first}
      </Text>
      <Ionicons name="chevron-forward" size={15} color={colors.textTertiary} />
    </Pressable>
  );
}

/** Reusable elsewhere (settings, profile header) — one avatar, one rule. */
export function Avatar({
  name,
  picture,
  size = 32,
}: {
  name?: string | null;
  picture?: string | null;
  size?: number;
}) {
  const { colors } = useTheme();
  // An uploaded avatar is served from ORA's authenticated API; one from a
  // social login is already an absolute public URL. `mediaUrl` handles both.
  const [headers, setHeaders] = useState<Record<string, string> | null>(null);
  const resolved = mediaUrl(picture);
  const needsAuth = !!picture && !/^https?:\/\//i.test(picture);
  useEffect(() => {
    let alive = true;
    if (needsAuth) mediaHeaders().then((h) => { if (alive) setHeaders(h); });
    return () => { alive = false; };
  }, [needsAuth, picture]);

  const initials = (name || '')
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0])
    .join('')
    .toUpperCase();

  if (resolved && (!needsAuth || headers)) {
    return (
      <Image
        source={needsAuth ? { uri: resolved, headers: headers || {} } : { uri: resolved }}
        style={{ width: size, height: size, borderRadius: size / 2 }}
        contentFit="cover"
        transition={140}
        cachePolicy="memory-disk"
        accessibilityLabel={name ? `Foto di ${name}` : 'Foto profilo'}
        testID="avatar-image"
      />
    );
  }

  return (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        backgroundColor: colors.accentMuted,
        alignItems: 'center',
        justifyContent: 'center',
      }}
      testID="avatar-initials"
    >
      <Text style={{ color: colors.accent, fontWeight: '700', fontSize: size * 0.38 }}>
        {initials || '·'}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    minHeight: 48,
    paddingHorizontal: 10,
    borderRadius: tokens.radius.md,
  },
  name: { flex: 1, fontSize: 14, fontWeight: '600' },
  pressed: { opacity: 0.7 },
});
