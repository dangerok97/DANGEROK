/**
 * Life Setup route — the guided first run.
 *
 * V3.3 replaced the conversational first launch with a guided path: structured
 * choices, one area of a life at a time, free text only behind "Altro". The
 * conversational screen remains in the tree (`LifeSetupConversationScreen`)
 * because it still owns the document flow and the resume path, and because a
 * rollback should not need a rewrite — but it is no longer what a person meets
 * on their first morning.
 *
 * Gate (`src/life-setup/gate.ts`) owns Home access; Home stays unaware.
 */
import { GuidedSetupScreen } from '@/src/life-setup/GuidedSetupScreen';

export default function LifeSetupScreen() {
  return <GuidedSetupScreen />;
}
