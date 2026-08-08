/**
 * Life Setup route — mounts conversational Life Experience behind the Gate.
 *
 * Sprint 1 placeholder remains at `PlaceholderLifeSetup` for rollback only.
 * Gate (`src/life-setup/gate.ts`) owns Home access; Home stays unaware.
 */
import { LifeSetupConversationScreen } from '@/src/life-setup/LifeSetupConversationScreen';

export default function LifeSetupScreen() {
  return <LifeSetupConversationScreen />;
}
