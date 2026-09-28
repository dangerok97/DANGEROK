/**
 * The background task, defined where the OS can find it.
 *
 *     OS EVENT != PRESENCE FACT.
 *
 * This file is the dumbest part of the system on purpose. It is woken by the
 * operating system, writes down where the phone was and when, and tries to
 * hand that over. It does not know which place it is near, whether that place
 * is home, whether arriving there matters, or whether anybody should be told.
 * All of that is decided by a state machine on the server that has the zones,
 * the hysteresis and the dwell — and by a person who named the place.
 *
 * A geofence crossing is treated exactly like any other fix: as one
 * observation, with coordinates and a timestamp. The native region is a way of
 * getting woken up cheaply, not a verdict. iOS gives one radius per region and
 * no dwell; believing it would reintroduce every bug Sprint 2 removed.
 *
 * `defineTask` must run at module scope, before the task is ever referenced,
 * which is why this module is imported for its side effect from the app root.
 */
import * as Location from 'expo-location';
import * as TaskManager from 'expo-task-manager';

import { remember } from './presenceBuffer';

export const LOCATION_TASK = 'ora-presence-location';
export const GEOFENCE_TASK = 'ora-presence-geofence';

function distanceMeters(a: { latitude: number; longitude: number }, b: { latitude: number; longitude: number }): number {
  const rad = Math.PI / 180;
  const dLat = (a.latitude - b.latitude) * rad;
  const dLon = (a.longitude - b.longitude) * rad;
  const v = Math.sin(dLat / 2) ** 2 + Math.cos(a.latitude * rad) *
    Math.cos(b.latitude * rad) * Math.sin(dLon / 2) ** 2;
  return 12742000 * Math.atan2(Math.sqrt(v), Math.sqrt(1 - v));
}

type LocationPayload = { locations?: Location.LocationObject[] };
type GeofencePayload = {
  eventType?: Location.GeofencingEventType;
  region?: Location.LocationRegion;
};

/**
 * Location updates while ORA is not in the foreground.
 *
 * Every fix is written down and nothing is interpreted. Errors are swallowed
 * rather than thrown: a background task that crashes is a background task the
 * OS stops waking up, and losing the whole capability is worse than losing one
 * reading.
 */
TaskManager.defineTask<LocationPayload>(LOCATION_TASK, async ({ data, error }) => {
  if (error || !data?.locations?.length) return;
  try {
    for (const fix of data.locations) {
      await remember({
        observed_at: new Date(fix.timestamp).toISOString(),
        latitude: fix.coords.latitude,
        longitude: fix.coords.longitude,
        accuracy_meters: fix.coords.accuracy ?? null,
        source: 'background_update',
      });
    }
    const runtime = await import('./presenceRuntime');
    if (await runtime.isEnabled()) await runtime.sendPending();
  } catch {
    /* see above: never throw out of a background task */
  }
});

/**
 * Crossing the edge of a monitored region.
 *
 * A region event contains its centre, not the phone's coordinates. Never
 * submit that centre as a GPS fix: on exit it would falsely claim the phone
 * is still inside. Take a real, recent fix; the server then applies dwell.
 */
TaskManager.defineTask<GeofencePayload>(GEOFENCE_TASK, async ({ data, error }) => {
  if (error || !data?.region) return;
  try {
    const { eventType } = data;
    let fix = await Location.getLastKnownPositionAsync({ maxAge: 15_000, requiredAccuracy: 100 });
    if (!fix) {
      // A geofence often wakes a paused location subscription. Give the OS a
      // short window for a measured fix, then leave the event unasserted.
      let timeout: ReturnType<typeof setTimeout> | undefined;
      try {
        fix = await Promise.race([
          Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced })
            .catch(() => null),
          new Promise<null>((resolve) => { timeout = setTimeout(() => resolve(null), 8_000); }),
        ]);
      } finally {
        if (timeout) clearTimeout(timeout);
      }
    }
    if (!fix) return;
    const inside = distanceMeters(fix.coords, data.region) <= data.region.radius;
    if (eventType === Location.GeofencingEventType.Exit && inside) return;
    if (eventType === Location.GeofencingEventType.Enter && !inside) return;
    await remember({
      observed_at: new Date(fix.timestamp).toISOString(),
      latitude: fix.coords.latitude,
      longitude: fix.coords.longitude,
      accuracy_meters: fix.coords.accuracy ?? null,
      source:
        eventType === Location.GeofencingEventType.Enter
          ? 'geofence_enter'
          : 'geofence_exit',
    });
    const runtime = await import('./presenceRuntime');
    if (await runtime.isEnabled()) await runtime.sendPending();
  } catch {
    /* as above */
  }
});
