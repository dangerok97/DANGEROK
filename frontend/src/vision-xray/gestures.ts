/** Pure pointer state. Multi-touch and cancelled gestures never become part taps. */
export const MIN_ZOOM = .65;
export const MAX_ZOOM = 3.2;
export const clampZoom = (value: number) => Number.isFinite(value) ? Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value)) : 1;
type Pointer = { x: number; y: number; startX: number; startY: number };
export type GestureDelta = { yaw: number; pitch: number; zoomFactor: number };
const NONE: GestureDelta = { yaw: 0, pitch: 0, zoomFactor: 1 };

export class VisionGestures {
  private pointers = new Map<number, Pointer>();
  private dragged = false;
  private multi = false;
  clear() { this.pointers.clear(); this.dragged = false; this.multi = false; }
  down(id: number, x: number, y: number) {
    if (!this.pointers.size) { this.dragged = false; this.multi = false; }
    this.pointers.set(id, { x, y, startX: x, startY: y });
    if (this.pointers.size > 1) this.multi = true;
  }
  move(id: number, x: number, y: number): GestureDelta {
    const p = this.pointers.get(id);
    if (!p) return NONE;
    const before = [...this.pointers.values()].slice(0, 2);
    const distance = before.length === 2 ? Math.hypot(before[0].x-before[1].x, before[0].y-before[1].y) : 0;
    const dx = x-p.x, dy = y-p.y;
    p.x = x; p.y = y;
    if (Math.hypot(x-p.startX, y-p.startY) > 6) this.dragged = true;
    if (this.pointers.size >= 2) {
      const after = [...this.pointers.values()].slice(0, 2);
      const next = Math.hypot(after[0].x-after[1].x, after[0].y-after[1].y);
      return { yaw: 0, pitch: 0, zoomFactor: distance > 8 ? Math.min(1.5, Math.max(.67, next/distance)) : 1 };
    }
    return this.dragged ? { yaw: dx*.007, pitch: dy*.006, zoomFactor: 1 } : NONE;
  }
  up(id: number, x: number, y: number, cancelled = false): boolean {
    const p = this.pointers.get(id);
    if (!p) return false;
    const tap = !cancelled && !this.multi && !this.dragged && Math.hypot(x-p.startX,y-p.startY) <= 6;
    this.pointers.delete(id);
    if (cancelled) this.dragged = true;
    return tap;
  }
}

/** Time-based easing: behaves the same on 30/60/120Hz devices. */
export function approach(current: number, target: number, elapsedMs: number, reducedMotion = false) {
  if (reducedMotion || Math.abs(current-target) < .001) return target;
  return current + (target-current)*(1-Math.exp(-Math.min(80, Math.max(0, elapsedMs)) / 110));
}
