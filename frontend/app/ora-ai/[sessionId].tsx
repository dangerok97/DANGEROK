/**
 * DEV / diagnostic AI Core harness — reuses production OraConversationScreen.
 * Production navigation must not depend on this route.
 */
import { useLocalSearchParams } from 'expo-router';
import { OraConversationScreen } from '@/src/components/ora/OraConversationScreen';
import type { OraEntryPoint } from '@/src/ora/oraNav';

/** @internal DEV harness */
export default function OraAiDevHarness() {
  const {
    sessionId,
    activeObject,
    objectId,
    planId,
    planItemId,
    entry,
  } = useLocalSearchParams<{
    sessionId?: string;
    activeObject?: string;
    objectId?: string;
    planId?: string;
    planItemId?: string;
    entry?: string;
  }>();

  const entryPoint = (
    ['home', 'ora', 'goal_workspace', 'continue', 'focus', 'object'].includes(String(entry || ''))
      ? entry
      : 'ora'
  ) as OraEntryPoint;

  return (
    <OraConversationScreen
      sessionId={sessionId}
      planId={planId}
      objectId={objectId || activeObject}
      planItemId={planItemId}
      entryPoint={entryPoint}
      devHarness
      testID="ora-ai-harness"
    />
  );
}
