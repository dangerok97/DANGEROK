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
import { useTheme } from '@/src/theme/ThemeProvider';
import { useBreakpoint } from '@/src/theme/responsive';
import { tokens } from '@/src/theme/tokens';
import { AMBIENT_BAR_HEIGHT, AMBIENT_RAIL_WIDTH } from './constants';
import { AMBIENT_NAV_ITEMS, type AmbientNavKey } from './navItems';
import { useDeclareShellMode } from './ShellModeContext';

export function AmbientTabBar({ state, navigation }: BottomTabBarProps) {
  useDeclareShellMode('ambient');
  const { colors, isDark } = useTheme();
  const insets = useSafeAreaInsets();
  const bp = useBreakpoint();
  const isRail = bp === 'desktop';

  const activeRoute = state.routes[state.index]?.name as string | undefined;

  const onPress = (routeName: AmbientNavKey) => {
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

  const items = AMBIENT_NAV_ITEMS.map((item) => {
    const focused = activeRoute === item.route;
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
          { opacity: pressed ? 0.7 : 1 },
        ]}
      >
        {item.center ? (
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
            <Text
              style={[
                styles.label,
                {
                  color: focused ? colors.textPrimary : colors.textTertiary,
                  fontWeight: focused ? '600' : '400',
                },
              ]}
              numberOfLines={1}
            >
              {item.label}
            </Text>
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
  });

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
        <View style={styles.railInner}>{items}</View>
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
        <View style={[styles.barRow, { minHeight: AMBIENT_BAR_HEIGHT }]}>{items}</View>
      </GlassContainer>
    </View>
  );
}

const styles = StyleSheet.create({
  barWrap: {
    position: 'absolute',
    left: 12,
    right: 12,
    bottom: 0,
  },
  glass: {
    borderRadius: tokens.radius['2xl'],
  },
  barRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 6,
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
    flex: 1.1,
  },
  label: {
    fontSize: 10,
    letterSpacing: 0.1,
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
    fontSize: 11,
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
  railInner: {
    flex: 1,
    width: AMBIENT_RAIL_WIDTH,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    paddingVertical: 12,
  },
  railItem: {
    width: AMBIENT_RAIL_WIDTH,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 3,
    minHeight: tokens.touch.min + 4,
    paddingVertical: 6,
    paddingHorizontal: 4,
  },
  railCenter: {
    marginVertical: 10,
  },
});
