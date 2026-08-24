import React from 'react';
import { StyleSheet, View, type ViewStyle } from 'react-native';

import { useBreakpoint } from '@/src/theme/responsive';
import { DECISION_COLUMN_MAX_WIDTH, CONTEXT_RAIL_WIDTH } from '@/src/shell';

type Props = {
  children: React.ReactNode;
  /**
   * Reserved for PX1.3+ (thread context, calendar context, linked documents,
   * activity, research). Passing nothing renders nothing — there is no empty
   * frame, no placeholder panel, and no space held open for content that does
   * not exist yet.
   */
  contextRail?: React.ReactNode;
  style?: ViewStyle;
  testID?: string;
};

/**
 * PageContainer — the decision column, centred in whatever space the shell
 * leaves it.
 *
 * The desktop complaint this exists to fix ("a small column on the left and a
 * huge void on the right") was never about the column being too narrow. It was
 * about screens that set no width at all, so their content either stretched
 * edge to edge or hugged the rail. Reading measure is a fixed human constant,
 * not a fraction of the viewport: past roughly 840px a line of text stops being
 * comfortable however big the monitor is. So the column stays put and the
 * *margins* absorb the extra width — equally on both sides, which is what makes
 * it read as composed rather than pushed aside.
 */
export function PageContainer({ children, contextRail, style, testID }: Props) {
  const bp = useBreakpoint();
  const isDesktop = bp === 'desktop';

  const column = (
    <View
      style={[
        styles.column,
        isDesktop || bp === 'tablet'
          ? { maxWidth: DECISION_COLUMN_MAX_WIDTH, alignSelf: 'center', width: '100%' }
          : null,
        style,
      ]}
      testID={testID}
    >
      {children}
    </View>
  );

  if (!isDesktop || !contextRail) return column;

  return (
    <View style={styles.withRail}>
      {column}
      <View style={[styles.contextRail, { width: CONTEXT_RAIL_WIDTH }]} testID="context-rail">
        {contextRail}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  column: {
    flex: 1,
    width: '100%',
  },
  withRail: {
    flex: 1,
    flexDirection: 'row',
    justifyContent: 'center',
  },
  contextRail: {
    flexShrink: 0,
  },
});
