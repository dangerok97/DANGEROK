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
 * V3.14.2 adds CHIAMATE between ORA and Attività, on the desktop rail
 * only — the phone bar has no room for a sixth label.
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

export type AmbientNavKey =
  | 'index'
  | 'contesti'
  | 'ora'
  | 'chiamate'
  | 'attivita'
  | 'documenti';
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
  /**
   * Shown on the desktop rail only.
   *
   * The phone bar is full, and this file's neighbour says why: six labelled
   * items do not fit 375px, and the first label to truncate is Documenti. The
   * rail has vertical room and no such limit, so a destination that earns a
   * place there does not automatically earn one down here.
   */
  railOnly?: boolean;
  /**
   * An address, for destinations that are not tab screens.
   *
   * Nobody uses it today: Chiamate started outside `(tabs)` and had to move
   * in, because a screen outside the navigator gets no rail — and a section
   * with no navigation and no way back is not a section. The field stays for
   * the next destination that genuinely lives elsewhere.
   */
  href?: string;
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
    /*
      Between ORA and Attività, and on the rail only.

      A call is something ORA did for you, so it sits with the doing — after
      the place you ask, before the place you watch. It is not in the phone
      bar: see `railOnly`.
    */
    key: 'chiamate',
    route: 'chiamate',
    label: 'Chiamate',
    accessibilityLabel: 'Chiamate di ORA',
    icon: 'call-outline',
    iconActive: 'call',
    railOnly: true,
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
