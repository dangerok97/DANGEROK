import assert from 'node:assert/strict';
import test from 'node:test';
import { parseMetres, projectRoom, surfaceLine, wallMeasurement } from './geometry.ts';
import type { HouseRoom, HouseScan, HouseSurface } from './types.ts';

function wall(id: string, length: number, x: number, z: number, angle = 0): HouseSurface {
  return { id, dimensions: { x: length, y: 2.8, z: 0 }, confidence: 'high',
    transform: [Math.cos(angle), 0, Math.sin(angle), 0, 0, 1, 0, 0, -Math.sin(angle), 0, Math.cos(angle), 0, x, 0, z, 1] };
}
const room: HouseRoom = { id: 'r1', name: 'Stanza', walls: [wall('a', 4, 0, 0), wall('b', 3, 2, 1.5, Math.PI / 2), wall('c', 4, 0, 3), wall('d', 3, -2, 1.5, Math.PI / 2)], doors: [], windows: [], openings: [], floors: [], objects: [] };

test('uses column-major translation and local X orientation for rotated walls', () => {
  const line = surfaceLine(wall('r', 4, 5, 7, Math.PI / 2))!;
  assert.ok(Math.abs(line.start.x - 5) < 1e-9);
  assert.equal(line.start.y, 5);
  assert.equal(line.end.y, 9);
});

test('projection preserves 4:3 aspect and centers walls inside phone viewport', () => {
  const plan = projectRoom(room, 320, 280);
  const a = plan.walls[0];
  const b = plan.walls[1];
  const la = Math.hypot(a.end.x - a.start.x, a.end.y - a.start.y);
  const lb = Math.hypot(b.end.x - b.start.x, b.end.y - b.start.y);
  assert.ok(Math.abs(la / lb - 4 / 3) < 1e-9);
  assert.equal((a.start.x + a.end.x) / 2, 160);
  for (const line of plan.walls) for (const p of [line.start, line.end]) {
    assert.ok(p.x >= 38 && p.x <= 282);
    assert.ok(p.y >= 38 && p.y <= 242);
  }
});

test('invalid or empty geometry cannot create NaN styles', () => {
  assert.equal(surfaceLine({ ...room.walls[0], transform: [NaN] }), null);
  assert.equal(surfaceLine({ ...room.walls[0], dimensions: { x: Infinity, y: 2, z: 0 } }), null);
  assert.deepEqual(projectRoom({ ...room, walls: [] }, 320, 280), { walls: [], doors: [], windows: [], scale: 1 });
  assert.equal(projectRoom(room, 0, 0).walls.length, 0);
});

test('verified quote remains separate and cannot mutate captured geometry', () => {
  const scan = { room_labels: [], wall_measurements: [{ room_id: 'r1', wall_id: 'a', length_m: 4.03, source: 'user_verified', verified_at: '2026-10-21T10:00:00Z' }] } as HouseScan;
  assert.equal(wallMeasurement(scan, room, room.walls[0]).length_m, 4.03);
  assert.equal(room.walls[0].dimensions.x, 4);
  assert.equal(wallMeasurement(scan, room, room.walls[1]).verified, null);
});

test('Italian metric input accepts comma and rejects ambiguity and non-finite values', () => {
  assert.equal(parseMetres(' 4,035 '), 4.035);
  assert.equal(parseMetres('4.2'), 4.2);
  for (const bad of ['-1', '0', 'NaN', 'Infinity', '1,2.3', '1.000,4', '12 m', '100.001', '']) assert.equal(parseMetres(bad), null);
});

test('room numbers: floor area, perimeter and paintable walls, verified lengths first', async () => {
  const { roomStats } = await import('./geometry.ts');
  const scan = { room_labels: [], wall_measurements: [] } as unknown as HouseScan;
  const stats = roomStats(scan, room);
  assert.ok(Math.abs((stats.floor_area_m2 ?? 0) - 12) < 1e-9);
  assert.equal(stats.floor_area_approximate, true);
  assert.equal(stats.perimeter_m, 14);
  assert.ok(Math.abs(stats.wall_area_m2 - 14 * 2.8) < 1e-9);
  const floored = { ...room, floors: [{ id: 'f', dimensions: { x: 4, y: 3, z: 0 }, transform: [], confidence: 'high' as const }] };
  assert.equal(roomStats(scan, floored).floor_area_approximate, false);
  const verified = { room_labels: [], wall_measurements: [{ room_id: 'r1', wall_id: 'a', length_m: 4.1, verified_at: '', source: 'user_verified' }] } as unknown as HouseScan;
  assert.ok(Math.abs(roomStats(verified, room).perimeter_m - 14.1) < 1e-9);
});
