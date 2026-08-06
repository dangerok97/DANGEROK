/**
 * After login/register: first-launch conversation if eligible.
 * Never opens a permanent Life Setup module/section.
 */
import { Router } from 'expo-router';
import { api } from '@/src/api/client';

export async function routeAfterAuth(router: Router): Promise<void> {
  try {
    const st = await api.lifeSetupStatus();
    if (st.ok && st.should_show) {
      router.replace('/life-setup' as any);
      return;
    }
  } catch {
    // Fail soft → Home
  }
  router.replace('/(tabs)' as any);
}
