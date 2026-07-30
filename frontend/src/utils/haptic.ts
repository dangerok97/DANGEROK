/**
 * Haptic wrapper that:
 *  - is a no-op on web
 *  - swallows errors silently
 *  - provides typed intents (tap, success, warning, error, medium)
 * so callers don't have to worry about platform / import details.
 */
import { Platform } from 'react-native';
import * as Haptics from 'expo-haptics';

type Intent = 'tap' | 'select' | 'success' | 'warning' | 'error' | 'medium' | 'heavy';

export async function haptic(intent: Intent) {
  if (Platform.OS === 'web') return;
  try {
    switch (intent) {
      case 'tap':
        await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
        break;
      case 'select':
        await Haptics.selectionAsync();
        break;
      case 'medium':
        await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
        break;
      case 'heavy':
        await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);
        break;
      case 'success':
        await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        break;
      case 'warning':
        await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
        break;
      case 'error':
        await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
        break;
    }
  } catch {}
}
