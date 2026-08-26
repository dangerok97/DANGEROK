/**
 * After login/register: Life Setup Gate → Home only when completed.
 */
import { Router } from 'expo-router';
import { routeByLifeSetupGate } from '@/src/life-setup/gate';

export async function routeAfterAuth(
  router: Router,
  userId: string,
  next?: string | null,
): Promise<void> {
  await routeByLifeSetupGate(router, userId, next);
}
