/**
 * One icon per part of a life, decided in one place.
 *
 * A person should recognise "Casa" or "Mobilità" before reading the word, and
 * they should recognise it the same way everywhere — in the path, in the
 * heading, in the rail, in Vita. Scattering the choice across components is
 * how the same area ends up with a house in one list and a building in
 * another.
 *
 * The key comes from the server (`LifeArea.icon_key`), which names the *idea*;
 * this maps the idea onto the icon set the app already uses. No second icon
 * system, no emoji: outline glyphs at one weight, quiet by default and
 * accented only where something is actually happening.
 */
import { Ionicons } from '@expo/vector-icons';

type IoniconName = React.ComponentProps<typeof Ionicons>['name'];

const BY_KEY: Record<string, IoniconName> = {
  home: 'home-outline',
  work: 'briefcase-outline',
  study: 'school-outline',
  car: 'car-outline',
  people: 'people-outline',
  assets: 'business-outline',
  finance: 'wallet-outline',
  shield: 'shield-outline',
  services: 'flash-outline',
  health: 'heart-outline',
};

/**
 * Anything unrecognised gets a neutral mark rather than a wrong one: an area
 * added tomorrow should look unfinished, not mislabelled.
 */
export function areaIconName(iconKey?: string | null): IoniconName {
  return BY_KEY[(iconKey || '').trim().toLowerCase()] || 'ellipse-outline';
}
