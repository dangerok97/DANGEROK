import type { HouseRoom, HouseScan, HouseSurface } from './types';

export type Point2 = { x: number; y: number };
export type PlanLine = { id: string; start: Point2; end: Point2; length_m: number; index: number };
export type PlanProjection = { walls: PlanLine[]; doors: PlanLine[]; windows: PlanLine[]; scale: number };

/** A RoomPlan wall's local X axis is its length; Y is its height. */
export function surfaceLine(surface: HouseSurface, index = 0): PlanLine | null {
  const t = surface.transform;
  const length = surface.dimensions.x;
  if (t.length !== 16 || !t.every(Number.isFinite) || !Number.isFinite(length) || length <= 0) return null;
  const dx = t[0] * length / 2;
  const dz = t[2] * length / 2;
  if (Math.hypot(dx, dz) < 0.00001) return null;
  return {
    id: surface.id, index, length_m: length,
    start: { x: t[12] - dx, y: t[14] - dz },
    end: { x: t[12] + dx, y: t[14] + dz },
  };
}

export function projectRoom(room: HouseRoom, width: number, height: number, padding = 38): PlanProjection {
  const walls = room.walls.map(surfaceLine).filter((line): line is PlanLine => line !== null);
  if (!walls.length || !Number.isFinite(width) || !Number.isFinite(height) || width <= padding * 2 || height <= padding * 2) {
    return { walls: [], doors: [], windows: [], scale: 1 };
  }
  const points = walls.flatMap(line => [line.start, line.end]);
  const minX = Math.min(...points.map(p => p.x));
  const maxX = Math.max(...points.map(p => p.x));
  const minY = Math.min(...points.map(p => p.y));
  const maxY = Math.max(...points.map(p => p.y));
  const spanX = Math.max(maxX - minX, 0.5);
  const spanY = Math.max(maxY - minY, 0.5);
  const scale = Math.min((width - 2 * padding) / spanX, (height - 2 * padding) / spanY);
  const centerX = (minX + maxX) / 2;
  const centerY = (minY + maxY) / 2;
  const point = (p: Point2): Point2 => ({ x: (p.x - centerX) * scale + width / 2, y: (p.y - centerY) * scale + height / 2 });
  const project = (line: PlanLine): PlanLine => ({ ...line, start: point(line.start), end: point(line.end) });
  const surfaces = (values: HouseSurface[]) => values.map(surfaceLine).filter((v): v is PlanLine => v !== null).map(project);
  return { walls: walls.map(project), doors: surfaces(room.doors), windows: surfaces(room.windows), scale };
}

export function roomName(scan: HouseScan, room: HouseRoom): string {
  return scan.room_labels.find(label => label.room_id === room.id)?.name || room.name;
}

export function wallMeasurement(scan: HouseScan, room: HouseRoom, wall: HouseSurface) {
  const verified = scan.wall_measurements.find(item => item.room_id === room.id && item.wall_id === wall.id);
  return { length_m: verified?.length_m ?? wall.dimensions.x, verified: verified ?? null };
}

export function formatMetres(value: number): string {
  return `${value.toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} m`;
}

export function parseMetres(input: string): number | null {
  const text = input.trim().replace(',', '.');
  if (!/^\d+(?:\.\d{1,3})?$/.test(text)) return null;
  const value = Number(text);
  return Number.isFinite(value) && value > 0 && value <= 100 ? value : null;
}
