import type { ComponentProps } from 'react';
// Type-only: `Ionicons` is referenced solely in `typeof` position below, so it
// must not become a runtime import (that would drag the native icon package
// into any plain-node consumer, including this module's tests).
import type { Ionicons } from '@expo/vector-icons';

/**
 * PX1.1 — Information Architecture 2.0.
 *
 *   HOME · VITA · ORA · ATTIVITÀ · DOCUMENTI      (+ account, set apart)
 *
 * What changed and why:
 *
 * - `contesti` is now labelled **Vita**. The route and its screen are
 *   untouched (PX1.5 owns that redesign) — this is the name the destination
 *   should have had: people have a life, not contexts.
 * - **Attività** is new, and deliberately a real destination rather than a
 *   menu item bolted on later: it is where ORA's own questions and updates
 *   will live (PX1.6). Its placeholder says what will be there, never
 *   "coming soon".
 * - **Documenti** is promoted out of Profilo. It was a primary surface hidden
 *   two taps deep behind an account menu.
 * - **Memoria** leaves the primary bar. It is a trust-and-configuration
 *   surface — something you visit to check what ORA knows, not somewhere you
 *   go daily. It stays reachable from Profilo.
 * - **Profilo** is no longer one of five equal cognitive destinations. On
 *   desktop it sits apart at the foot of the rail, as an account affordance.
 */

export type AmbientNavKey = 'index' | 'contesti' | 'ora' | 'attivita' | 'documenti';
export type AmbientAccountKey = 'profilo';

export type AmbientNavItem = {
  key: AmbientNavKey | AmbientAccountKey;
  /** expo-router Tabs screen name */
  route: AmbientNavKey | AmbientAccountKey;
  label: string;
  accessibilityLabel: string;
  icon: ComponentProps<typeof Ionicons>['name'];
  iconActive: ComponentProps<typeof Ionicons>['name'];
  /** Center ORA entry — distinct, not FAB */
  center?: boolean;
};

/** The five cognitive destinations. Order is the order people move through them. */
export const AMBIENT_NAV_ITEMS: AmbientNavItem[] = [
  {
    key: 'index',
    route: 'index',
    label: 'Home',
    accessibilityLabel: 'Home',
    icon: 'home-outline',
    iconActive: 'home',
  },
  {
    key: 'contesti',
    route: 'contesti',
    label: 'Vita',
    accessibilityLabel: 'La tua vita',
    icon: 'layers-outline',
    iconActive: 'layers',
  },
  {
    key: 'ora',
    route: 'ora',
    label: 'ORA',
    accessibilityLabel: 'Apri ORA',
    /** Calm mark — not + / FAB / sparkle */
    icon: 'ellipse-outline',
    iconActive: 'ellipse',
    center: true,
  },
  {
    key: 'attivita',
    route: 'attivita',
    label: 'Attività',
    accessibilityLabel: 'Attività di ORA',
    icon: 'pulse-outline',
    iconActive: 'pulse',
  },
  {
    key: 'documenti',
    route: 'documenti',
    label: 'Documenti',
    accessibilityLabel: 'Documenti',
    icon: 'document-text-outline',
    iconActive: 'document-text',
  },
];

/**
 * Account, kept off the primary set on purpose. Rendered at the foot of the
 * desktop rail; on phone it stays in the bar, because a bottom bar has no
 * "apart" position and hiding the only route to your own account behind a
 * gesture would be worse than the small inconsistency.
 */
export const AMBIENT_ACCOUNT_ITEM: AmbientNavItem = {
  key: 'profilo',
  route: 'profilo',
  label: 'Profilo',
  accessibilityLabel: 'Profilo e account',
  icon: 'person-circle-outline',
  iconActive: 'person-circle',
};
