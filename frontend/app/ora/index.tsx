/**
 * ORA without a session yet.
 *
 * This used to be a separate, simpler start screen, and that was the bug: the
 * Workspace hands off to `/ora?planId=…&objectId=…&planItemId=…&entry=…` when
 * no session exists, and this route read none of it. The first message went out
 * as a bare `entry_point: "ora"` with no plan and no object, so the user landed
 * in a conversation that had never heard of the goal they had just been working
 * on — and "questa parte non mi convince" referred to nothing.
 *
 * There is only one conversation surface now. It already knows how to start a
 * session, carry the context into it and take over the URL afterwards.
 */
import { useLocalSearchParams } from 'expo-router';

import { OraConversationScreen } from '@/src/components/ora/OraConversationScreen';
import { oraEntryPointFrom } from '@/src/ora/oraNav';

export default function OraProductionStart() {
  const { planId, objectId, planItemId, documentId, questionId, opportunityId, needId, goalId, entry } = useLocalSearchParams<{
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
      planId={planId}
      objectId={objectId}
      planItemId={planItemId}
      documentId={documentId}
      questionId={questionId}
      opportunityId={opportunityId}
      needId={needId}
      goalId={goalId}
      entryPoint={oraEntryPointFrom(entry)}
      testID="ora-production-start"
    />
  );
}
