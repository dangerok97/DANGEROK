import type { ComponentProps } from 'react';
import { Ionicons } from '@expo/vector-icons';

export type AmbientNavKey = 'index' | 'contesti' | 'ora' | 'memoria' | 'profilo';

export type AmbientNavItem = {
  key: AmbientNavKey;
  /** expo-router Tabs screen name */
  route: AmbientNavKey;
  label: string;
  accessibilityLabel: string;
  icon: ComponentProps<typeof Ionicons>['name'];
  iconActive: ComponentProps<typeof Ionicons>['name'];
  /** Center ORA entry — distinct, not FAB */
  center?: boolean;
};

/** Primary Ambient IA — Documenti/Aggiungi stay reachable but off the bar. */
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
    label: 'Contesti',
    accessibilityLabel: 'Contesti',
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
    key: 'memoria',
    route: 'memoria',
    label: 'Memoria',
    accessibilityLabel: 'Memoria',
    icon: 'search-outline',
    iconActive: 'search',
  },
  {
    key: 'profilo',
    route: 'profilo',
    label: 'Profilo',
    accessibilityLabel: 'Profilo',
    icon: 'person-outline',
    iconActive: 'person',
  },
];
