import type { ComponentProps } from 'react';
import type { Ionicons } from '@expo/vector-icons';

/**
 * Which contextual visual a card should wear.
 *
 * ## Why this is not domain routing
 *
 * Nothing here reads a title, a description, or any words the user wrote. It
 * reads `HomeItem.type` — an enum the backend already emits (`event`, `study`,
 * `payment`, …) as part of its own presentation contract — plus, when that is
 * absent, `source_type` and `card_type`, which are equally structural.
 *
 * The rule PX1.1 and the V2.9.x audits protect against is a *branch on meaning*
 * invented in the client: `if (title.includes('viaggio'))`. That would make the
 * frontend a second, worse classifier competing with the reasoning core. This
 * is the opposite: the core already decided what kind of thing this is, and the
 * interface is only choosing how to dress that decision. If the backend adds a
 * type tomorrow, this falls back gracefully instead of guessing.
 *
 * ## Why the visual matters at all
 *
 * A card the user can recognise before reading it is a card that costs them
 * less. The visual is there to say "this is that thing you already know about"
 * at a glance — which is why it is derived from what the thing *is*, and never
 * chosen for decoration.
 */

export type VisualKind =
  | 'moment'      // something happening at a time
  | 'journey'     // something away from home
  | 'ledger'      // money moving
  | 'learning'    // preparation, knowledge
  | 'review'      // something needing the user's eye
  | 'place'       // somewhere to be
  | 'message'     // a reply owed
  | 'task'        // something to do
  | 'discovery'   // something ORA noticed
  | 'thread';     // something already in progress

export type VisualDescriptor = {
  kind: VisualKind;
  icon: ComponentProps<typeof Ionicons>['name'];
  /**
   * Gradient stops, always derived from the Quiet Premium palette rather than
   * invented: warm neutrals with a single restrained hue shift. No card should
   * shout, and no two kinds should be told apart by colour alone (the icon
   * carries the meaning — see the accessibility rule about status never being
   * colour-only).
   */
  tint: [string, string];
};

/**
 * Warm sand and clay, with one restrained indigo family — the same off-white
 * world as the rest of Quiet Premium, one step deeper so the panel reads as an
 * image area rather than a hole in the card.
 *
 * The first pass used near-white cool greys. On a cream hero they disappeared:
 * the visual looked like an empty white rectangle, which is exactly what a
 * placeholder looks like. A picture area has to have some body.
 */
const TINTS: Record<VisualKind, [string, string]> = {
  moment:    ['#DFE1EF', '#F0EEE8'],
  journey:   ['#D9E3E6', '#EFEDE7'],
  ledger:    ['#E9E0D0', '#F2EEE6'],
  learning:  ['#DFE0EE', '#EFEDE7'],
  review:    ['#EDDFCC', '#F2EDE4'],
  place:     ['#DCE7DE', '#EEEEE6'],
  message:   ['#E4DEEC', '#F0EDE7'],
  task:      ['#E2E0DA', '#F1EFE9'],
  discovery: ['#DEE1F0', '#F0EEE9'],
  thread:    ['#E7E1D6', '#F2EFE8'],
};

const ICONS: Record<VisualKind, ComponentProps<typeof Ionicons>['name']> = {
  moment: 'calendar-outline',
  journey: 'navigate-outline',
  ledger: 'card-outline',
  learning: 'book-outline',
  review: 'eye-outline',
  place: 'location-outline',
  message: 'chatbubble-ellipses-outline',
  task: 'checkmark-circle-outline',
  discovery: 'sparkles-outline',
  thread: 'play-circle-outline',
};

/**
 * The backend's own item taxonomy, mapped once. Exhaustive over the current
 * `HomeItemType` union; anything unknown becomes a `task`, which is the honest
 * default for "something of yours that needs doing".
 */
const BY_ITEM_TYPE: Record<string, VisualKind> = {
  event: 'moment',
  travel: 'journey',
  bill: 'ledger',
  payment: 'ledger',
  study: 'learning',
  verify: 'review',
  needs_review: 'review',
  visit: 'place',
  reply: 'message',
  activity: 'task',
  insight: 'discovery',
  resume: 'thread',
  generic: 'task',
};

/** Secondary signal when an item carries no type of its own. */
const BY_SOURCE_TYPE: Record<string, VisualKind> = {
  calendar: 'moment',
  calendar_event: 'moment',
  document: 'review',
  documents: 'review',
  suggestion: 'discovery',
  insight: 'discovery',
  situation: 'thread',
  goal: 'task',
  plan: 'task',
};

type VisualInput = {
  type?: string | null;
  subtype?: string | null;
  source_type?: string | null;
  card_type?: string | null;
};

export function visualKindFor(input: VisualInput | null | undefined): VisualKind {
  if (!input) return 'task';
  const byType = input.type ? BY_ITEM_TYPE[input.type] : undefined;
  if (byType) return byType;
  const byCard = input.card_type ? BY_ITEM_TYPE[input.card_type] : undefined;
  if (byCard) return byCard;
  const bySource = input.source_type ? BY_SOURCE_TYPE[input.source_type] : undefined;
  if (bySource) return bySource;
  return 'task';
}

export function visualFor(input: VisualInput | null | undefined): VisualDescriptor {
  const kind = visualKindFor(input);
  return { kind, icon: ICONS[kind], tint: TINTS[kind] };
}

/** Every kind, for tests and for a future visual gallery. */
export const ALL_VISUAL_KINDS = Object.keys(TINTS) as VisualKind[];
