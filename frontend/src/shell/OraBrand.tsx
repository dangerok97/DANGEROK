import { StyleSheet, View } from 'react-native';
import { Image } from 'expo-image';

import { useTheme } from '@/src/theme/ThemeProvider';

/**
 * The ORA brand mark in the navigation rail — the official asset, rendered
 * whole. Never redrawn in code: the file at `assets/images/ora-logo.png` is
 * the mark, and this component only sizes and places it.
 */

/**
 * The official mark. A static require so the bundler resolves it at build time
 * and a missing file fails loudly — the previous defensive try/catch swallowed
 * the failure and silently drew the fallback instead, which is exactly the kind
 * of quiet wrong-but-plausible result that survives review.
 */
const OFFICIAL_LOGO = require('@/assets/images/ora-logo.png');

export function OraBrand({ size = 40 }: { size?: number }) {
  const { colors } = useTheme();

  return (
    /*
      The mark, not a heading.

      As `accessibilityRole="header"` this rendered an <h1> in the navigation
      rail, so every page announced two level-one headings — the product's name
      and then the page's. A screen-reader user jumping by heading landed on
      the logo first, on every screen. It is a logo: it says what it is and
      stops competing with the title of the page you are on.
    */
    <View style={styles.wrap} testID="ora-brand" accessibilityLabel="ORA">
      {/*
        The asset carries the ring *and* the wordmark, so the component renders
        it whole rather than pairing the mark with type of our own — that is
        what "do not redraw the logo" means in practice.
      */}
      {/*
        Sized from the asset's own 1890x832 ratio (~2.27:1) rather than a
        guessed multiplier: the earlier 3.6x reserved far more width than the
        artwork fills, so `contain` shrank the mark to fit the box and the
        brand read as an afterthought.
      */}
      <Image
        source={OFFICIAL_LOGO}
        style={{ width: size * 2.27, height: size }}
        contentFit="contain"
        contentPosition="left center"
        transition={0}
        accessibilityLabel="ORA"
        testID="ora-brand-logo"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flexDirection: 'row', alignItems: 'center', gap: 9 },
});
