/**
 * A small local queue for observations the phone made while nobody was looking.
 *
 * Background callbacks arrive when they arrive — in a tunnel, on aeroplane
 * mode, at three in the morning with no signal. An observation that cannot be
 * delivered is not an observation that should be dropped: dwell is measured
 * against when the fix was *taken*, so a batch flushed an hour later still
 * describes the hour it describes.
 *
 * Deliberately a list in AsyncStorage. This is a phone, not a message broker,
 * and the failure mode of anything more elaborate is worse than the failure
 * mode of losing a handful of fixes.
 *
 * Each entry carries its own id and the server treats repeated deliveries as
 * the same sighting, because an OS may hand the same callback twice and one
 * evening at home must stay one evening at home.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';

const KEY = 'ora.presence.buffer.v1';
/** Beyond this the oldest go: a queue that grows without limit is a leak. */
const MAX_ENTRIES = 200;

export type BufferedObservation = {
  event_id: string;
  observed_at: string;
  latitude: number;
  longitude: number;
  accuracy_meters?: number | null;
  /** What woke the phone up: a location update, or crossing a region. */
  source: 'background_update' | 'geofence_enter' | 'geofence_exit' | 'foreground';
  delivered: boolean;
};

function newId(): string {
  return `evt_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

async function read(): Promise<BufferedObservation[]> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as BufferedObservation[]) : [];
  } catch {
    // A corrupt buffer is not worth crashing a background task over.
    return [];
  }
}

async function write(entries: BufferedObservation[]): Promise<void> {
  try {
    await AsyncStorage.setItem(KEY, JSON.stringify(entries.slice(-MAX_ENTRIES)));
  } catch {
    /* If it cannot be stored it cannot be sent. Nothing here can fix that. */
  }
}

export async function remember(
  observation: Omit<BufferedObservation, 'event_id' | 'delivered'>,
): Promise<void> {
  const entries = await read();
  entries.push({ ...observation, event_id: newId(), delivered: false });
  await write(entries);
}

export async function pending(): Promise<BufferedObservation[]> {
  return (await read()).filter((e) => !e.delivered);
}

/**
 * Send what is waiting, oldest first, and forget what was accepted.
 *
 * Order matters: the state machine reads a sequence, and delivering this
 * morning's departure after this evening's arrival would describe a day
 * nobody had. Anything that fails stays queued for the next attempt.
 */
export async function flush(
  send: (entry: BufferedObservation) => Promise<boolean>,
): Promise<{ sent: number; left: number }> {
  const entries = await read();
  const queue = entries.filter((e) => !e.delivered).sort((a, b) =>
    a.observed_at.localeCompare(b.observed_at),
  );

  let sent = 0;
  for (const entry of queue) {
    let ok = false;
    try {
      ok = await send(entry);
    } catch {
      ok = false;
    }
    if (!ok) break;
    entry.delivered = true;
    sent += 1;
  }

  const left = entries.filter((e) => !e.delivered);
  await write(left);
  return { sent, left: left.length };
}

export async function clear(): Promise<void> {
  try {
    await AsyncStorage.removeItem(KEY);
  } catch {
    /* nothing to do */
  }
}
