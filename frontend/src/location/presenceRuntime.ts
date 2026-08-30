/**
 * Turning Presence Intelligence on, off, and keeping it honest in between.
 *
 * Three jobs, and nothing else:
 *
 * **Permission, in two steps.** Foreground is asked when somebody uses
 * something that needs it. Background is asked only when they switch this
 * capability on, because "always" is a large thing to ask and asking it during
 * a first run is how an app gets refused for good. Saying no is a supported
 * answer: ORA goes on working, without continuous presence.
 *
 * **Monitoring that matches reality.** Regions are re-registered whenever the
 * set of places changes — added, removed, resized, logged out — because a
 * geofence around a flat somebody moved out of is a phone waking up for
 * nothing, forever.
 *
 * **Reconciliation.** Whenever ORA is opened it takes one fix and sends it.
 * Phones get switched off, tasks get killed, callbacks get lost; the stored
 * state is a belief, and a belief nobody checks becomes "sei a casa" said to
 * somebody at the airport.
 *
 * Battery: no `watchPositionAsync` at high accuracy, ever. Regions do the
 * waking, distance and time intervals bound the rest, and the balanced
 * accuracy class is what a hundred-metre zone actually needs.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';

import { api } from '@/src/api/client';
import { flush, remember } from './presenceBuffer';
import { GEOFENCE_TASK, LOCATION_TASK } from './presenceTask';

const ENABLED_KEY = 'ora.presence.enabled.v1';

/**
 * How far the phone must move before it is worth another fix, and how long
 * between them at most. Generous on purpose: presence is about buildings, and
 * a person who has moved less than 100 m has not changed which one they are in.
 */
const DISTANCE_INTERVAL_M = 100;
const TIME_INTERVAL_MS = 5 * 60 * 1000;

/** iOS monitors a limited number of regions; the OS itself caps it around 20. */
const MAX_REGIONS = 18;

export type PresenceSupport = {
  /** Whether this build can do background presence at all. */
  supported: boolean;
  reason?: string;
};

export type PresencePermissions = {
  foreground: 'granted' | 'denied' | 'undetermined';
  background: 'granted' | 'denied' | 'undetermined';
};

function native(): boolean {
  return Platform.OS === 'ios' || Platform.OS === 'android';
}

async function locationModule() {
  // Imported lazily so the web bundle never pulls a native-only module in.
  return (await import('expo-location')) as typeof import('expo-location');
}

export function support(): PresenceSupport {
  if (!native()) {
    return {
      supported: false,
      reason:
        'Il browser non può riconoscere i tuoi luoghi quando ORA è chiusa. ' +
        'Serve l’app installata.',
    };
  }
  return { supported: true };
}

export async function permissions(): Promise<PresencePermissions> {
  if (!native()) {
    return { foreground: 'undetermined', background: 'denied' };
  }
  const Location = await locationModule();
  const fg = await Location.getForegroundPermissionsAsync();
  const bg = await Location.getBackgroundPermissionsAsync();
  const read = (s: { status: string }) =>
    s.status === 'granted' ? 'granted' : s.status === 'denied' ? 'denied' : 'undetermined';
  return { foreground: read(fg), background: read(bg) } as PresencePermissions;
}

/** Foreground only. Asked when something the person is doing needs it. */
export async function askForeground(): Promise<boolean> {
  if (!native()) return false;
  const Location = await locationModule();
  const { status } = await Location.requestForegroundPermissionsAsync();
  return status === 'granted';
}

/**
 * Background, asked second and never first.
 *
 * The OS refuses to consider "always" before "while using" has been granted,
 * and asking in that order is also the only order that makes sense to a person.
 */
export async function askBackground(): Promise<boolean> {
  if (!native()) return false;
  const Location = await locationModule();
  const fg = await Location.getForegroundPermissionsAsync();
  if (fg.status !== 'granted') {
    const asked = await Location.requestForegroundPermissionsAsync();
    if (asked.status !== 'granted') return false;
  }
  const { status } = await Location.requestBackgroundPermissionsAsync();
  return status === 'granted';
}

export async function isEnabled(): Promise<boolean> {
  try {
    return (await AsyncStorage.getItem(ENABLED_KEY)) === '1';
  } catch {
    return false;
  }
}

/**
 * Switch continuous presence on.
 *
 * Returns what actually happened rather than a boolean, because "denied" and
 * "not supported on this build" are different things to say to somebody.
 */
export async function enable(): Promise<{ ok: boolean; reason?: string }> {
  const can = support();
  if (!can.supported) return { ok: false, reason: can.reason };
  if (!(await askBackground())) {
    return {
      ok: false,
      reason:
        'Senza il permesso in background ORA non può accorgersi degli ' +
        'ingressi e delle uscite quando è chiusa. Tutto il resto continua a ' +
        'funzionare.',
    };
  }

  const Location = await locationModule();
  await Location.startLocationUpdatesAsync(LOCATION_TASK, {
    // Balanced, not Highest: a hundred-metre zone does not need a
    // three-metre fix, and asking for one is what empties a battery.
    accuracy: Location.Accuracy.Balanced,
    distanceInterval: DISTANCE_INTERVAL_M,
    timeInterval: TIME_INTERVAL_MS,
    pausesUpdatesAutomatically: true,
    showsBackgroundLocationIndicator: false,
    foregroundService: {
      notificationTitle: 'ORA riconosce i tuoi luoghi',
      notificationBody:
        'Serve per accorgersi di quando arrivi o esci. Puoi disattivarlo dal Profilo.',
    },
  });

  await AsyncStorage.setItem(ENABLED_KEY, '1');
  await syncRegions();
  return { ok: true };
}

/**
 * Switch it off, completely and immediately.
 *
 * Nothing is deleted here. Off means the phone stops watching; what ORA
 * already knows is the person's to keep or erase, separately and on purpose.
 */
export async function disable(): Promise<void> {
  await AsyncStorage.setItem(ENABLED_KEY, '0');
  if (!native()) return;
  const Location = await locationModule();
  const TaskManager = await import('expo-task-manager');

  if (await TaskManager.isTaskRegisteredAsync(LOCATION_TASK)) {
    await Location.stopLocationUpdatesAsync(LOCATION_TASK).catch(() => undefined);
  }
  if (await TaskManager.isTaskRegisteredAsync(GEOFENCE_TASK)) {
    await Location.stopGeofencingAsync(GEOFENCE_TASK).catch(() => undefined);
  }
}

/**
 * Point the OS at the places that currently exist.
 *
 * Called after anything that changes them. The native radius is the wider exit
 * circle so the phone is woken slightly early rather than slightly late — the
 * server still decides with entry, exit and dwell, and being woken for nothing
 * costs a callback while being woken late costs a missed arrival.
 */
export async function syncRegions(): Promise<{ regions: number }> {
  if (!native() || !(await isEnabled())) return { regions: 0 };

  const Location = await locationModule();
  const TaskManager = await import('expo-task-manager');

  let places: Awaited<ReturnType<typeof api.placesList>>['places'] = [];
  try {
    places = (await api.placesList()).places;
  } catch {
    return { regions: 0 };
  }

  const regions = places
    .filter((p) => p.state === 'confirmed' && p.has_coordinates && p.zone_center)
    .slice(0, MAX_REGIONS)
    .map((p) => ({
      identifier: p.id,
      latitude: p.zone_center!.latitude,
      longitude: p.zone_center!.longitude,
      radius: p.zone_center!.exit_radius_m,
      notifyOnEnter: true,
      notifyOnExit: true,
    }));

  if (await TaskManager.isTaskRegisteredAsync(GEOFENCE_TASK)) {
    await Location.stopGeofencingAsync(GEOFENCE_TASK).catch(() => undefined);
  }
  if (regions.length) {
    await Location.startGeofencingAsync(GEOFENCE_TASK, regions);
  }
  return { regions: regions.length };
}

/**
 * One fix now, plus whatever is still queued.
 *
 * Called when ORA opens. This is the correction for everything the background
 * could not do: a phone that was off, a task the system killed, a callback
 * that never arrived.
 */
export async function reconcile(): Promise<{ sent: number; left: number }> {
  if (native()) {
    try {
      const Location = await locationModule();
      const fg = await Location.getForegroundPermissionsAsync();
      if (fg.status === 'granted') {
        const fix = await Location.getCurrentPositionAsync({
          accuracy: Location.Accuracy.Balanced,
        });
        await remember({
          observed_at: new Date(fix.timestamp).toISOString(),
          latitude: fix.coords.latitude,
          longitude: fix.coords.longitude,
          accuracy_meters: fix.coords.accuracy ?? null,
          source: 'foreground',
        });
      }
    } catch {
      /* no fix is a normal outcome indoors; the queue is still worth flushing */
    }
  }

  return flush(async (entry) => {
    try {
      await api.placesRecordObservation({
        latitude: entry.latitude,
        longitude: entry.longitude,
        accuracy_meters: entry.accuracy_meters ?? undefined,
        observed_at: entry.observed_at,
        event_id: entry.event_id,
      });
      return true;
    } catch {
      return false;
    }
  });
}

/** Logging out must not leave a phone watching for somebody who left. */
export async function shutdown(): Promise<void> {
  await disable();
  const { clear } = await import('./presenceBuffer');
  await clear();
}
