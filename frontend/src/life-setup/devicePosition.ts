/**
 * Where the device thinks it is — asked the way the product already asks.
 *
 * The browser's own permission prompt is the permission flow: there is no
 * second consent screen to build and no expo-location dependency to add. A
 * refusal, a timeout and an unsupported browser all come back the same way,
 * as `null`, because from here they mean one thing: ask the person instead.
 *
 * Coordinates never reach the interface. They go straight to the reverse
 * geocoder and what comes back is a town — somebody setting up their home
 * should read "Tarquinia", not a pair of decimals.
 */
export type DevicePosition = { lat: number; lon: number };

export function requestDevicePosition(): Promise<DevicePosition | null> {
  const geo = (globalThis as any)?.navigator?.geolocation;
  if (!geo?.getCurrentPosition) return Promise.resolve(null);
  return new Promise((resolve) => {
    try {
      geo.getCurrentPosition(
        (pos: { coords?: { latitude?: number; longitude?: number } }) => {
          const lat = pos?.coords?.latitude;
          const lon = pos?.coords?.longitude;
          if (typeof lat === 'number' && typeof lon === 'number') {
            resolve({ lat, lon });
          } else {
            resolve(null);
          }
        },
        () => resolve(null),
        { enableHighAccuracy: false, timeout: 12000, maximumAge: 120000 },
      );
    } catch {
      resolve(null);
    }
  });
}
