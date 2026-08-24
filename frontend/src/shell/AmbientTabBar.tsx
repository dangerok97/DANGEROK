/**
 * Ambient navigation — Quiet Premium.
 * Phone/tablet: floating bottom bar (GlassContainer + solid fallback).
 * Desktop breakpoint: compact left rail (fixed AMBIENT_RAIL_WIDTH) via tabBarPosition left.
 */
import { Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import type { BottomTabBarProps } from '@react-navigation/bottom-tabs';
import * as Haptics from 'expo-haptics';

import { GlassContainer } from '@/src/components/ui/GlassContainer';
import { useAuth } from '@/src/contexts/AuthContext';
import { OraBrand } from './OraBrand';
import { RailAccount } from './RailAccount';
import { useTheme } from '@/src/theme/ThemeProvider';
import { useBreakpoint } from '@/src/theme/responsive';
import { tokens } from '@/src/theme/tokens';
import { MIN_READABLE_FONT_SIZE } from '@/src/theme/typography';
import { AMBIENT_BAR_HEIGHT, AMBIENT_RAIL_WIDTH } from './constants';
import {
  AMBIENT_ACCOUNT_ITEM,
  AMBIENT_NAV_ITEMS,
  type AmbientNavItem,
  type AmbientNavKey,
} from './navItems';
import { useDeclareShellMode } from './ShellModeContext';

export function AmbientTabBar({ state, navigation }: BottomTabBarProps) {
  useDeclareShellMode('ambient');
  const { colors, isDark } = useTheme();
  const { user } = useAuth();
  const insets = useSafeAreaInsets();
  const bp = useBreakpoint();
  const isRail = bp === 'desktop';

  const activeRoute = state.routes[state.index]?.name as string | undefined;

  const onPress = (routeName: AmbientNavKey | 'profilo') => {
    if (Platform.OS !== 'web') {
      void Haptics.selectionAsync();
    }
    const route = state.routes.find((r) => r.name === routeName);
    if (!route) {
      navigation.navigate(routeName as never);
      return;
    }
    const event = navigation.emit({
      type: 'tabPress',
      target: route.key,
      canPreventDefault: true,
    });
    if (!event.defaultPrevented) {
      navigation.navigate(routeName as never);
    }
  };

  const renderItem = (item: AmbientNavItem) => {
    const focused = activeRoute === item.route;
    /*
      Account is not a destination — the desktop rail says so with a divider
      and its own footer. The phone bar has no "apart" position, so it says the
      same thing the only way a bar can: the five destinations carry words,
      account carries just its icon. That also returns the ~11px that made
      "Documenti" truncate once labels reached the 12px readability floor —
      six labelled items simply do not fit 375px, and the label that should
      give way is the one that is not a place you go.
    */
    const isAccount = item.key === AMBIENT_ACCOUNT_ITEM.key;
    const iconOnly = isAccount && !isRail;
    return (
      <Pressable
        key={item.key}
        onPress={() => onPress(item.route)}
        accessibilityRole="tab"
        accessibilityState={{ selected: focused }}
        accessibilityLabel={item.accessibilityLabel}
        testID={`ambient-tab-${item.key}`}
        style={({ pressed }) => [
          isRail ? styles.railItem : styles.barItem,
          item.center && (isRail ? styles.railCenter : styles.barCenter),
          iconOnly && styles.barAccount,
          // The rail marks the current place with a soft filled pill rather
          // than colour alone — legible before you read the label.
          isRail && focused && { backgroundColor: colors.accentMuted },
          { opacity: pressed ? 0.7 : 1 },
        ]}
      >
        {/*
          The circular ORA mark belongs to the phone bar, where it anchors the
          centre. On the rail it made ORA look like a section label rather than
          somewhere you go, so there it is an ordinary destination: icon,
          label, full-width hit target, same selected pill as its neighbours.
        */}
        {item.center && !isRail ? (
          <View
            style={[
              styles.oraMark,
              isRail && styles.oraMarkRail,
              {
                backgroundColor: 'transparent',
                borderColor: focused
                  ? colors.textSecondary
                  : isRail
                    ? 'transparent'
                    : colors.borderStrong,
              },
            ]}
          >
            <Text
              style={[
                styles.oraLabel,
                {
                  color: focused ? colors.textPrimary : colors.textTertiary,
                  fontWeight: focused ? '700' : '500',
                },
              ]}
            >
              ORA
            </Text>
          </View>
        ) : (
          <>
            <Ionicons
              name={focused ? item.iconActive : item.icon}
              size={isRail ? 20 : 22}
              color={focused ? colors.textPrimary : colors.textTertiary}
            />
            {iconOnly ? null : (
              <Text
                style={[
                  styles.label,
                  {
                    color: focused ? colors.textPrimary : colors.textTertiary,
                    /*
                      The rail signals the active tab by weight alone. The bar
                      already has its own dot, so bolding there is redundant —
                      and it costs real width: bold "Documenti" overflows the
                      slot that fits it at regular weight, so the label would
                      truncate only while selected. A constant weight also
                      keeps the row from reflowing every time you switch tab.
                    */
                    fontWeight: isRail ? (focused ? '600' : '400') : '500',
                  },
                ]}
                numberOfLines={1}
              >
                {item.label}
              </Text>
            )}
            {/* Mobile only: non-color active cue. Rail uses weight alone. */}
            {!isRail ? (
              focused ? (
                <View style={[styles.activeDot, { backgroundColor: colors.accent }]} />
              ) : (
                <View style={styles.activeDotSpacer} />
              )
            ) : null}
          </>
        )}
      </Pressable>
    );
  };

  const primaryItems = AMBIENT_NAV_ITEMS.map(renderItem);

  if (isRail) {
    return (
      <View
        style={[
          styles.railWrap,
          {
            width: AMBIENT_RAIL_WIDTH,
            paddingTop: Math.max(insets.top, 16),
            paddingBottom: Math.max(insets.bottom, 16),
            backgroundColor: colors.backgroundSecondary,
            borderRightColor: colors.divider,
          },
        ]}
        testID="ambient-rail"
        accessibilityLabel="Navigazione Ambient"
      >
        {/*
          Brand, destinations, then the person. The gap between the last
          destination and the account is the point: it is what says Profilo is
          not a sixth place to go.
        */}
        <View style={styles.railBrand}>
          <OraBrand />
        </View>
        <View style={styles.railInner}>{primaryItems}</View>
        <View style={[styles.railAccount, { borderTopColor: colors.divider }]}>
          <RailAccount
            name={user?.name}
            email={user?.email}
            picture={user?.picture}
            onPress={() => onPress(AMBIENT_ACCOUNT_ITEM.route)}
            selected={activeRoute === AMBIENT_ACCOUNT_ITEM.route}
          />
        </View>
      </View>
    );
  }

  const bottomPad = Math.max(insets.bottom, 10);

  return (
    <View
      pointerEvents="box-none"
      style={[styles.barWrap, { paddingBottom: bottomPad }]}
      testID="ambient-tab-bar"
      accessibilityLabel="Navigazione Ambient"
    >
      <GlassContainer glassRole="tabBar" style={styles.glass} intensity={isDark ? 56 : 42}>
        {/*
          Phone keeps account in the bar. A bottom bar has no "set apart"
          position, and stranding the only route to your own account behind a
          gesture would cost more than this small divergence from the rail.
          The final phone IA is PX1.x work, not something to improvise here.
        */}
        <View style={[styles.barRow, { minHeight: AMBIENT_BAR_HEIGHT }]}>
          {primaryItems}
          {renderItem(AMBIENT_ACCOUNT_ITEM)}
        </View>
      </GlassContainer>
    </View>
  );
}

const styles = StyleSheet.create({
  barWrap: {
    position: 'absolute',
    /*
      6, not 12. Five labelled destinations plus an account affordance at the
      12px readability floor genuinely fill a 375px bar — the longest label was
      losing by under a pixel. Reclaiming the outer margin (and the centre
      item's extra flex below) buys real headroom instead of another exact tie
      that the next locale or font would break.
    */
    left: 6,
    right: 6,
    bottom: 0,
  },
  glass: {
    borderRadius: tokens.radius['2xl'],
  },
  barRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 2,
    paddingVertical: 6,
  },
  barItem: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 2,
    minHeight: tokens.touch.min,
    paddingVertical: 4,
  },
  barCenter: {
    flex: 1,
  },
  /**
   * Icon-only account slot: takes what it needs, not an equal fifth.
   * Explicit grow/shrink/basis rather than `flex: 0` — that shorthand resolves
   * to a zero basis here and collapsed the button to zero width, leaving the
   * only route to the account untappable.
   */
  barAccount: {
    flexGrow: 0,
    flexShrink: 0,
    flexBasis: 44,
    minWidth: 44,
  },
  label: {
    // PX1.1: was 10 — below the readable floor, on chrome the user reads on
    // every screen, forever. At 12px the longest label ("Documenti") needs
    // 59.1px in a 58.4px slot, so the decorative 0.1 tracking goes: legibility
    // earns the pixels, letter-spacing does not.
    fontSize: MIN_READABLE_FONT_SIZE,
    letterSpacing: 0,
  },
  activeDot: {
    width: 3,
    height: 3,
    borderRadius: 1.5,
    marginTop: 1,
  },
  activeDotSpacer: {
    width: 3,
    height: 3,
    marginTop: 1,
  },
  oraMark: {
    minWidth: 48,
    minHeight: 48,
    borderRadius: tokens.radius.full,
    borderWidth: StyleSheet.hairlineWidth * 2,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 10,
  },
  oraMarkRail: {
    minWidth: 44,
    minHeight: 44,
    borderWidth: StyleSheet.hairlineWidth,
  },
  oraLabel: {
    fontSize: MIN_READABLE_FONT_SIZE,
    letterSpacing: 0.8,
  },
  /**
   * Fixed-width rail — never flex:1 (that caused 50/50 with the scene).
   * Height fills the tab-bar slot via alignSelf: 'stretch'.
   */
  railWrap: {
    width: AMBIENT_RAIL_WIDTH,
    alignSelf: 'stretch',
    borderRightWidth: StyleSheet.hairlineWidth,
  },
  railBrand: {
    paddingHorizontal: 16,
    paddingBottom: 26,
    paddingTop: 6,
  },
  railInner: {
    flex: 1,
    width: AMBIENT_RAIL_WIDTH,
    alignItems: 'stretch',
    gap: 2,
    paddingHorizontal: 10,
  },
  railAccount: {
    width: AMBIENT_RAIL_WIDTH,
    alignItems: 'center',
    paddingTop: 10,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  /** A labelled row, not a glyph: icon, then the word, left aligned. */
  railItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    minHeight: 46,
    paddingHorizontal: 12,
    borderRadius: tokens.radius.md,
  },
  railCenter: {},
});
