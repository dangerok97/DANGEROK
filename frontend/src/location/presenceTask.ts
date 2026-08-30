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
  } catch {
    /* see above: never throw out of a background task */
  }
});

/**
 * Crossing the edge of a monitored region.
 *
 * Recorded as an observation with the region's own centre when the payload
 * carries no fix of its own — which is the honest thing to store, since what
 * the OS actually told us is "you are somewhere near this region", not a
 * position. The server decides what, if anything, that means.
 */
TaskManager.defineTask<GeofencePayload>(GEOFENCE_TASK, async ({ data, error }) => {
  if (error || !data?.region) return;
  try {
    const { region, eventType } = data;
    await remember({
      observed_at: new Date().toISOString(),
      latitude: region.latitude,
      longitude: region.longitude,
      accuracy_meters: region.radius ?? null,
      source:
        eventType === Location.GeofencingEventType.Enter
          ? 'geofence_enter'
          : 'geofence_exit',
    });
  } catch {
    /* as above */
  }
});
