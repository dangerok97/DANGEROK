/**
 * Production ORA conversation — AI Core session.
 */
import { useLocalSearchParams } from 'expo-router';

import { OraConversationScreen } from '@/src/components/ora/OraConversationScreen';
import { oraEntryPointFrom } from '@/src/ora/oraNav';

export default function OraProductionSession() {
  const { sessionId, opening, planId, objectId, planItemId, documentId, questionId, opportunityId, needId, goalId, entry, draft } = useLocalSearchParams<{
    sessionId?: string;
    opening?: string;
    planId?: string;
    objectId?: string;
    planItemId?: string;
    documentId?: string;
    questionId?: string;
    opportunityId?: string;
    needId?: string;
    goalId?: string;
    entry?: string;
    draft?: string;
  }>();

  return (
    <OraConversationScreen
      sessionId={sessionId}
      openingKey={opening === '1' ? sessionId : undefined}
      planId={planId}
      objectId={objectId}
      planItemId={planItemId}
      documentId={documentId}
      questionId={questionId}
      opportunityId={opportunityId}
      needId={needId}
      goalId={goalId}
      initialDraft={draft}
      entryPoint={oraEntryPointFrom(entry)}
      testID="ora-production"
    />
  );
}
