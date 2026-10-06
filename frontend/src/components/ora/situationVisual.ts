import type { ComponentProps } from 'react';
import type { Ionicons } from '@expo/vector-icons';
import type { KnowledgeStar } from './presence/knowledge';

/**
 * A bounded visual vocabulary selected by cognition through Situation.icon_key.
 * No statement/keyword parsing lives here: unknown concepts always fall back.
 */
const ICONS: Record<string, ComponentProps<typeof Ionicons>['name']> = {
  laundry: 'shirt-outline',
  shirt: 'shirt-outline',
  activity: 'walk-outline',
  travel: 'navigate-outline',
  car: 'car-outline',
  airplane: 'airplane-outline',
  timer: 'timer-outline',
  delivery: 'cube-outline',
  package: 'cube-outline',
  shopping: 'cart-outline',
  event: 'calendar-outline',
  calendar: 'calendar-outline',
  health: 'medkit-outline',
  medicine: 'medical-outline',
  weather: 'rainy-outline',
  finance: 'wallet-outline',
  payment: 'card-outline',
  people: 'people-outline',
  document: 'document-text-outline',
  call: 'call-outline',
  home: 'home-outline',
  food: 'restaurant-outline',
  fitness: 'barbell-outline',
  work: 'briefcase-outline',
  study: 'school-outline',
  sleep: 'moon-outline',
  repair: 'construct-outline',
  key: 'key-outline',
  pet: 'paw-outline',
  alarm: 'alarm-outline',
  other: 'bookmark-outline',
};

export function situationIcon(key?: string | null): ComponentProps<typeof Ionicons>['name'] {
  return ICONS[String(key || '').trim().toLowerCase()] || 'bookmark-outline';
}

export function situationTitle(star?: KnowledgeStar | null): string {
  const value = String(star?.semantic_kind || '').trim();
  return value || 'Situazione attiva';
}

export function firstSituationState(star?: KnowledgeStar | null): string | null {
  return (
    String(star?.current_state_summary || '').trim()
    || String(star?.facts?.[0] || '').trim()
    || null
  );
}
