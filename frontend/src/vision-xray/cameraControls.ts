/** Camera controls are independent of the study-model camera.
 * Torch uses the actual video track, never a white-screen imitation.
 * 1–3x is explicitly DIGITAL: the same cover/zoom crop drives preview and AI.
 * No ImageCapture/browser sniffing and no invented hardware support.
 */
export type CameraTrack = Pick<MediaStreamTrack, 'readyState' | 'stop'> & {
  getCapabilities?: () => unknown;
  getSettings?: () => unknown;
  applyConstraints?: (value: MediaTrackConstraints) => Promise<void>;
};
export type TorchState = { supported: boolean; on: boolean; busy: boolean; message: string };
export const TORCH_UNAVAILABLE = 'Flash non disponibile con questa fotocamera o browser.';
export const CAMERA_ZOOM_MAX = 3;
export const clampCameraZoom = (n: number) => Number.isFinite(n) ? Math.min(CAMERA_ZOOM_MAX, Math.max(1, n)) : 1;
export type Crop = { x: number; y: number; width: number; height: number };

/** Source rectangle corresponding exactly to CSS object-fit:cover + centred scale. */
export function cameraCrop(sw: number, sh: number, vw: number, vh: number, zoom = 1): Crop {
  if ([sw, sh, vw, vh].some(n => !Number.isFinite(n) || n <= 0)) throw new Error('Dimensioni fotocamera non valide');
  const scale = Math.max(vw / sw, vh / sh) * clampCameraZoom(zoom);
  const width = Math.min(sw, vw / scale), height = Math.min(sh, vh / scale);
  return { x: (sw - width) / 2, y: (sh - height) / 2, width, height };
}
export function sameCrop(a: Crop, b: Crop): boolean {
  return (['x', 'y', 'width', 'height'] as const).every(k => Math.abs(a[k] - b[k]) < .1);
}
export function drawCameraCrop(ctx: CanvasRenderingContext2D, source: CanvasImageSource, crop: Crop, width: number, height: number) {
  ctx.drawImage(source, crop.x, crop.y, crop.width, crop.height, 0, 0, width, height);
}
function read(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? value as Record<string, unknown> : {};
}
function setting(track: CameraTrack): boolean | undefined {
  try { const value = read(track.getSettings?.()).torch; return typeof value === 'boolean' ? value : undefined; }
  catch { return undefined; }
}

/** Serialises torch writes and drops callbacks after disposal. `on` requires a
 * getSettings() confirmation; a resolved promise alone may have ignored a constraint.
 */
export class CameraTorch {
  private disposed = false;
  private state: TorchState;
  constructor(private track: CameraTrack, private changed: (state: TorchState) => void) {
    let capability: unknown;
    try { capability = read(track.getCapabilities?.()).torch; } catch { /* conservative fallback */ }
    const supported = Boolean(track.applyConstraints) && track.readyState === 'live' &&
      (capability === true || (Array.isArray(capability) && capability.includes(true)));
    this.state = { supported, on: setting(track) === true, busy: false, message: supported ? '' : TORCH_UNAVAILABLE };
  }
  snapshot(): TorchState { return { ...this.state }; }
  private emit(patch: Partial<TorchState>) {
    if (this.disposed) return;
    this.state = { ...this.state, ...patch }; this.changed(this.snapshot());
  }
  async toggle(): Promise<void> {
    if (this.disposed || this.state.busy || !this.state.supported || this.track.readyState !== 'live') return;
    const target = !this.state.on;
    this.emit({ busy: true, message: '' });
    let deadline: ReturnType<typeof setTimeout> | undefined;
    let failed = false;
    const operation = Promise.resolve().then(() => {
      if (!this.disposed) return this.track.applyConstraints!({ advanced: [{ torch: target } as MediaTrackConstraintSet] });
    });
    // Should a browser finish only after stop/timeout, never leave a late torch-on.
    void operation.then(() => { if (this.disposed || failed) this.forceOff(); }).catch(() => {});
    try {
      await Promise.race([operation, new Promise<never>((_, reject) => {
        deadline = setTimeout(() => reject(new Error('timeout')), 4000);
      })]);
      if (this.disposed) return;
      const actual = setting(this.track);
      if (actual !== target) {
        this.forceOff();
        this.emit({ on: actual === true, supported: actual === true,
          message: 'Il browser non conferma il comando del flash. Usa Spegni per fermare la fotocamera.' });
      } else this.emit({ on: actual, message: '' });
    } catch {
      failed = true;
      if (!this.disposed) {
        this.forceOff();
        this.emit({ on: setting(this.track) === true,
          message: 'Non riesco a cambiare il flash. Puoi riprovare o spegnere la fotocamera.' });
      }
    } finally { if (deadline) clearTimeout(deadline); this.emit({ busy: false }); }
  }
  private forceOff() {
    try {
      const op = this.track.applyConstraints?.({ advanced: [{ torch: false } as MediaTrackConstraintSet] });
      void op?.then(() => { if (!this.disposed) this.emit({ on: setting(this.track) === true }); }).catch(() => {});
    } catch { /* stopping the track remains the unconditional off operation */ }
  }
  dispose() {
    if (this.disposed) return;
    this.disposed = true;
    this.forceOff();
    this.track.stop();
  }
}
