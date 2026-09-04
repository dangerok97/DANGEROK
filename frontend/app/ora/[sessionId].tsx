/**
 * Production ORA conversation — AI Core session.
 */
import { useLocalSearchParams } from 'expo-router';

import { OraConversationScreen } from '@/src/components/ora/OraConversationScreen';
import { oraEntryPointFrom } from '@/src/ora/oraNav';

export default function OraProductionSession() {
  const { sessionId, planId, objectId, planItemId, documentId, questionId, opportunityId, needId, goalId, entry } = useLocalSearchParams<{
    sessionId?: string;
    planId?: string;
    objectId?: string;
    planItemId?: string;
    documentId?: string;
    questionId?: string;
    opportunityId?: string;
    needId?: string;
    goalId?: string;
    entry?: string;
  }>();

  return (
    <OraConversationScreen
      sessionId={sessionId}
      planId={planId}
      objectId={objectId}
      planItemId={planItemId}
      documentId={documentId}
      questionId={questionId}
      opportunityId={opportunityId}
      needId={needId}
      goalId={goalId}
      entryPoint={oraEntryPointFrom(entry)}
      testID="ora-production"
    />
  );
}
