import type { HouseCapture } from './types';
import {
  HouseScanError,
  type HouseScanAvailability,
  type OraRoomPlanNativeModule,
} from './nativeTypes.ts';

/** No camera or native-module lookup occurs on web or an unsupported platform. */
export function createHouseScanAdapter(
  platform: string,
  loadModule: () => OraRoomPlanNativeModule | null,
): OraRoomPlanNativeModule {
  const native = (): OraRoomPlanNativeModule | null => (platform === 'ios' ? loadModule() : null);

  async function getAvailability(): Promise<HouseScanAvailability> {
    if (platform === 'web') return { supported: false, reason: 'web_not_supported' };
    if (platform !== 'ios') return { supported: false, reason: 'platform_not_supported' };
    const module = native();
    if (!module) return { supported: false, reason: 'native_build_required' };
    return module.getAvailability();
  }

  async function scan(): Promise<HouseCapture> {
    const availability = await getAvailability();
    const module = native();
    if (!availability.supported || !module) {
      throw new HouseScanError(
        'ERR_ROOMPLAN_UNSUPPORTED',
        availability.reason === 'requires_lidar'
          ? 'La scansione richiede un iPhone o iPad con LiDAR.'
          : availability.reason === 'requires_ios17'
            ? 'Per scansionare aggiorna il dispositivo a iOS 17 o successivo.'
            : 'Apri la versione iPhone di ORA con la funzione di scansione installata.',
      );
    }
    // Camera permission is requested by the native module only after this
    // explicit action. Denied permission and cancellation retain their codes.
    return module.scan();
  }

  async function cancel(): Promise<void> {
    await native()?.cancel();
  }

  return { getAvailability, scan, cancel };
}
