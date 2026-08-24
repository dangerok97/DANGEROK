import { memo, useEffect, useState } from 'react';
import { StyleSheet, View, type ImageStyle, type StyleProp, type ViewStyle } from 'react-native';
import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';

import { tokens } from '@/src/theme/tokens';
import { mediaHeaders, mediaUrl } from '@/src/api/client';
import { visualFor, type VisualKind } from './visualKind';

type Props = {
  /**
   * A real picture, when one exists: a place photo, a document preview, a
   * project cover. Nothing in the Home payload carries one today — the field
   * exists so that the day the presentation layer emits a `visual_key` or an
   * image reference, cards start showing it without a single call site
   * changing.
   */
  imageSource?: string | null;
  /** Structural metadata the visual is derived from. */
  item?: {
    type?: string | null;
    subtype?: string | null;
    source_type?: string | null;
    card_type?: string | null;
  } | null;
  /** Override the derived kind (rare — prefer letting the item decide). */
  visualKind?: VisualKind;
  /**
   * The image is on its way. Shown as a quiet shimmer over the composition
   * rather than a spinner: nothing is broken, and the card is fully usable
   * without it — so the state should be felt, not announced.
   */
  generating?: boolean;
  /** hero: large side panel · card: inset thumb · row: compact square */
  size?: 'hero' | 'card' | 'row';
  /**
   * What the picture means to someone who cannot see it. Leave undefined for
   * the generated fallback: it carries no information the text does not
   * already state, so it is decorative and must be hidden from screen readers
   * rather than announced as "gradient with a calendar icon".
   */
  accessibilityLabel?: string;
  /** Same box either way — the two render paths must stay interchangeable. */
  style?: StyleProp<ViewStyle & ImageStyle>;
  testID?: string;
};

const DIMENSIONS: Record<NonNullable<Props['size']>, { radius: number; icon: number }> = {
  // The hero mark is deliberately modest: it is one element of a composition,
  // not the composition itself. A 64px glyph in the middle of a panel is what
  // made the first pass look like an empty placeholder.
  hero: { radius: tokens.radius.lg, icon: 26 },
  card: { radius: tokens.radius.md, icon: 22 },
  row: { radius: tokens.radius.sm, icon: 18 },
};

/**
 * ContextualCardVisual — the picture a card wears.
 *
 * **Contextual imagery is semantic, not decorative.** Its job is to let someone
 * recognise a situation before they finish reading it, which is why it is
 * derived from what the item *is* (see `visualKind.ts`) and never chosen to
 * fill space. A random photo on every card would be worse than none: it would
 * teach the eye that the image means nothing.
 *
 * Two modes, one contract:
 *
 * - `imageSource` → the real thing, through `expo-image` (cached, lazily
 *   decoded, fixed aspect so nothing jumps while it loads).
 * - otherwise → a generated field: a restrained gradient from the Quiet
 *   Premium palette plus the mark of its kind. It is deliberately abstract.
 *   ORA cannot invent a photograph of someone's exhibition without either
 *   sending their content to an image service or generating one, and both are
 *   out of bounds — so the honest fallback is a surface that says "this kind
 *   of thing", quietly, and gets out of the way.
 */
export const ContextualCardVisual = memo(function ContextualCardVisual({
  imageSource,
  item,
  visualKind,
  generating,
  size = 'card',
  accessibilityLabel,
  style,
  testID,
}: Props) {
  /*
    Generated visuals are served from ORA's own API, which is user-scoped and
    therefore authenticated. The path arrives app-relative, so it is resolved
    against the API origin, and the bearer token travels as a header — a card
    image is still the user's private data and is not made public to save a
    round trip.
  */
  const [headers, setHeaders] = useState<Record<string, string> | null>(null);
  useEffect(() => {
    let alive = true;
    if (imageSource) {
      mediaHeaders().then((h) => { if (alive) setHeaders(h); });
    }
    return () => { alive = false; };
  }, [imageSource]);

  const descriptor = visualFor(item);
  const kind = visualKind ?? descriptor.kind;
  const { radius, icon } = DIMENSIONS[size];
  const tint = visualKind ? visualFor({ type: visualKind }).tint : descriptor.tint;

  const resolved = mediaUrl(imageSource);
  if (resolved && headers) {
    return (
      <Image
        source={{ uri: resolved, headers }}
        style={[styles.base, { borderRadius: radius }, style] as StyleProp<ImageStyle>}
        contentFit="cover"
        transition={180}
        cachePolicy="memory-disk"
        accessible={!!accessibilityLabel}
        accessibilityLabel={accessibilityLabel}
        testID={testID}
      />
    );
  }

  return (
    <View
      style={[styles.base, { borderRadius: radius }, style] as StyleProp<ViewStyle>}
      // Generated, and carrying nothing the card's own words do not: decorative
      // by definition, so it is skipped rather than described.
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      testID={testID}
    >
      <LinearGradient
        colors={tint}
        start={{ x: 0.15, y: 0 }}
        end={{ x: 0.85, y: 1 }}
        style={StyleSheet.absoluteFill}
      />

      {/*
        An abstract still life, not an icon on a field.

        The first version centred one large glyph in a grey panel, and it read
        exactly like what it was: an empty slot waiting for a picture. A
        composition reads as a choice. These overlapping soft forms echo the
        way an editorial photograph is arranged — something tall behind,
        something round beside it, a horizon — so the card looks designed for
        an image even while it is standing in for one. The mark of the item's
        kind sits inside the composition rather than dominating it.
      */}
      {size !== 'row' ? (
        <View style={StyleSheet.absoluteFill} pointerEvents="none">
          <View style={[styles.formTall, { backgroundColor: 'rgba(255,255,255,0.72)' }]} />
          <View style={[styles.formRound, { backgroundColor: 'rgba(61,74,140,0.13)' }]} />
          <View style={[styles.formBar, { backgroundColor: 'rgba(61,74,140,0.10)' }]} />
          <View style={[styles.horizon, { backgroundColor: 'rgba(61,74,140,0.14)' }]} />
        </View>
      ) : null}

      <Ionicons
        name={descriptor.icon}
        size={icon}
        color="rgba(61, 74, 140, 0.42)"
        style={size === 'row' ? undefined : styles.markOffset}
      />
    </View>
  );
});

const styles = StyleSheet.create({
  base: {
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
    // Every instance is given an explicit box by its parent; this is the floor
    // so a missing size can never collapse a card's layout to zero height.
    minHeight: 40,
    minWidth: 40,
  },
  /** A breath of light while the real image is being drawn. */
  generating: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(255,255,255,0.28)',
  },
  /** Tall form, back left — the "framed picture" of the composition. */
  formTall: {
    position: 'absolute',
    left: '18%',
    top: '20%',
    width: '34%',
    height: '52%',
    borderRadius: 10,
  },
  /** Round form, front right. */
  formRound: {
    position: 'absolute',
    right: '18%',
    top: '38%',
    width: '26%',
    aspectRatio: 1,
    borderRadius: 999,
  },
  /** Low horizontal form, foreground. */
  formBar: {
    position: 'absolute',
    left: '30%',
    bottom: '22%',
    width: '40%',
    height: '12%',
    borderRadius: 8,
  },
  /** A ground line, so the forms sit rather than float. */
  horizon: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: '20%',
    height: StyleSheet.hairlineWidth * 2,
  },
  /** Keeps the mark out of the centre, where it would read as a placeholder. */
  markOffset: {
    position: 'absolute',
    left: '16%',
    bottom: '12%',
  },
});
