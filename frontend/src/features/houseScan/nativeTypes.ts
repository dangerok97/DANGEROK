import type { HouseCapture } from './types';

export type HouseScanAvailabilityReason =
  | 'supported'
  | 'requires_ios17'
  | 'requires_lidar'
  | 'native_build_required'
  | 'web_not_supported'
  | 'platform_not_supported';

export type HouseScanAvailability = {
  supported: boolean;
  reason: HouseScanAvailabilityReason;
  camera_permission?: 'authorized' | 'not_determined' | 'denied' | 'restricted';
};

export type HouseScanErrorCode =
  | 'ERR_ROOMPLAN_CANCELLED'
  | 'ERR_ROOMPLAN_CAMERA_PERMISSION'
  | 'ERR_ROOMPLAN_INTERRUPTED'
  | 'ERR_ROOMPLAN_BUSY'
  | 'ERR_ROOMPLAN_UNSUPPORTED'
  | 'ERR_ROOMPLAN_CONFIGURATION'
  | 'ERR_ROOMPLAN_EMPTY'
  | 'ERR_ROOMPLAN_CAPTURE'
  | 'ERR_ROOMPLAN_PROCESSING';

export interface OraRoomPlanNativeModule {
  getAvailability(): Promise<HouseScanAvailability>;
  scan(): Promise<HouseCapture>;
  cancel(): Promise<void>;
}

export class HouseScanError extends Error {
  readonly code: HouseScanErrorCode;

  constructor(code: HouseScanErrorCode, message: string) {
    super(message);
    this.name = 'HouseScanError';
    this.code = code;
  }
}
