/**
 * Production ORA conversation — AI Core session.
 */
import { useLocalSearchParams } from 'expo-router';

import { OraConversationScreen } from '@/src/components/ora/OraConversationScreen';
import { oraEntryPointFrom } from '@/src/ora/oraNav';

export default function OraProductionSession() {
  const { sessionId, planId, objectId, planItemId, documentId, entry } = useLocalSearchParams<{
    sessionId?: string;
    planId?: string;
    objectId?: string;
    planItemId?: string;
    documentId?: string;
    entry?: string;
  }>();

  return (
    <OraConversationScreen
      sessionId={sessionId}
      planId={planId}
      objectId={objectId}
      planItemId={planItemId}
      documentId={documentId}
      entryPoint={oraEntryPointFrom(entry)}
      testID="ora-production"
    />
  );
}
