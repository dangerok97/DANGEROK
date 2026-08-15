/**
 * Production ORA conversation — AI Core session.
 */
import { useLocalSearchParams } from 'expo-router';
import { OraConversationScreen } from '@/src/components/ora/OraConversationScreen';
import type { OraEntryPoint } from '@/src/ora/oraNav';

export default function OraProductionSession() {
  const { sessionId, planId, objectId, planItemId, entry } = useLocalSearchParams<{
    sessionId?: string;
    planId?: string;
    objectId?: string;
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
      objectId={objectId}
      planItemId={planItemId}
      entryPoint={entryPoint}
      testID="ora-production"
    />
  );
}
