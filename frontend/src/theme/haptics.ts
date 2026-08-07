/**
 * ORA Quiet Premium — semantic haptics.
 * Maps intent → expo-haptics style (callers wire expo-haptics when available).
 */

export type HapticIntent =
  | 'selection'
  | 'success'
  | 'warning'
  | 'error'
  | 'impactLight'
  | 'impactMedium'
  | 'impactHeavy'
  | 'notification';

export type HapticSpec = {
  type: 'selection' | 'notification' | 'impact';
  style?: 'success' | 'warning' | 'error' | 'light' | 'medium' | 'heavy';
};

export const haptics: Record<HapticIntent, HapticSpec> = {
  selection: { type: 'selection' },
  success: { type: 'notification', style: 'success' },
  warning: { type: 'notification', style: 'warning' },
  error: { type: 'notification', style: 'error' },
  impactLight: { type: 'impact', style: 'light' },
  impactMedium: { type: 'impact', style: 'medium' },
  impactHeavy: { type: 'impact', style: 'heavy' },
  notification: { type: 'notification', style: 'success' },
};

/** Fire haptic if expo-haptics is present (no hard dependency in theme). */
export async function triggerHaptic(intent: HapticIntent): Promise<void> {
  try {
    // Dynamic require keeps theme pack usable if haptics unavailable (web/tests).
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const Haptics = require('expo-haptics');
    const spec = haptics[intent];
    if (spec.type === 'selection') {
      await Haptics.selectionAsync();
      return;
    }
    if (spec.type === 'notification') {
      const map = {
        success: Haptics.NotificationFeedbackType.Success,
        warning: Haptics.NotificationFeedbackType.Warning,
        error: Haptics.NotificationFeedbackType.Error,
      } as const;
      await Haptics.notificationAsync(map[spec.style as 'success' | 'warning' | 'error']);
      return;
    }
    const impactMap = {
      light: Haptics.ImpactFeedbackStyle.Light,
      medium: Haptics.ImpactFeedbackStyle.Medium,
      heavy: Haptics.ImpactFeedbackStyle.Heavy,
    } as const;
    await Haptics.impactAsync(impactMap[spec.style as 'light' | 'medium' | 'heavy']);
  } catch {
    // Haptics optional — silent no-op
  }
}
