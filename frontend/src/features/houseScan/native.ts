import { requireOptionalNativeModule } from 'expo';
import { Platform } from 'react-native';

import { createHouseScanAdapter } from './nativeAdapter';
import type { OraRoomPlanNativeModule } from './nativeTypes';

const adapter = createHouseScanAdapter(Platform.OS, () =>
  requireOptionalNativeModule<OraRoomPlanNativeModule>('OraRoomPlan'),
);

export const getAvailability = adapter.getAvailability;
export const scan = adapter.scan;
export const cancel = adapter.cancel;
export const getHouseScanAvailability = getAvailability;
export const scanHouse = scan;
export const cancelHouseScan = cancel;
export type { HouseScanAvailability, HouseScanAvailabilityReason, HouseScanErrorCode } from './nativeTypes';
