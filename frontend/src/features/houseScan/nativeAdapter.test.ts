import assert from 'node:assert/strict';
import test from 'node:test';

import { createHouseScanAdapter } from './nativeAdapter.ts';
import { HouseScanError, type OraRoomPlanNativeModule } from './nativeTypes.ts';
import type { HouseCapture } from './types';

const capture = {
  schema_version: 1,
  capture_id: 'native-result',
  source: 'apple_roomplan',
  captured_at: '2026-10-21T12:00:00Z',
  rooms: [],
} as HouseCapture;

test('web stays honest and never initializes a native camera module', async () => {
  const adapter = createHouseScanAdapter('web', () => {
    throw new Error('A web entry must not load RoomPlan.');
  });
  assert.deepEqual(await adapter.getAvailability(), { supported: false, reason: 'web_not_supported' });
  await assert.rejects(adapter.scan(), { code: 'ERR_ROOMPLAN_UNSUPPORTED' });
  await adapter.cancel();
});

test('Expo Go or an older native build has an actionable unsupported state', async () => {
  const adapter = createHouseScanAdapter('ios', () => null);
  assert.deepEqual(await adapter.getAvailability(), { supported: false, reason: 'native_build_required' });
  await assert.rejects(adapter.scan(), { code: 'ERR_ROOMPLAN_UNSUPPORTED' });
});

test('a device without LiDAR is never sent to capture even when the module exists', async () => {
  let scanCalls = 0;
  const adapter = createHouseScanAdapter('ios', () => ({
    getAvailability: async () => ({ supported: false, reason: 'requires_lidar' }),
    scan: async () => { scanCalls += 1; return capture; },
    cancel: async () => {},
  }));
  await assert.rejects(adapter.scan(), { code: 'ERR_ROOMPLAN_UNSUPPORTED' });
  assert.equal(scanCalls, 0);
});

test('permission is requested by native scan, not by the availability check', async () => {
  let scanCalls = 0;
  const module: OraRoomPlanNativeModule = {
    getAvailability: async () => ({ supported: true, reason: 'supported', camera_permission: 'not_determined' }),
    scan: async () => { scanCalls += 1; return capture; },
    cancel: async () => {},
  };
  const adapter = createHouseScanAdapter('ios', () => module);
  await adapter.getAvailability();
  assert.equal(scanCalls, 0);
  assert.equal(await adapter.scan(), capture);
  assert.equal(scanCalls, 1);
});

test('permission denial and cancellation keep stable native error codes', async () => {
  for (const code of ['ERR_ROOMPLAN_CAMERA_PERMISSION', 'ERR_ROOMPLAN_CANCELLED'] as const) {
    const error = new HouseScanError(code, 'Native error');
    const adapter = createHouseScanAdapter('ios', () => ({
      getAvailability: async () => ({ supported: true, reason: 'supported' }),
      scan: async () => { throw error; },
      cancel: async () => {},
    }));
    await assert.rejects(adapter.scan(), (received) => received === error);
  }
});
