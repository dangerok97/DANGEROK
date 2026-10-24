/** Metres, ARKit right-handed coordinates, column-major 4 × 4 transforms. */
export type Point3 = { x: number; y: number; z: number };
export type ScanConfidence = 'high' | 'medium' | 'low' | 'unknown';
export type HouseSurface = {
  id: string;
  dimensions: Point3;
  transform: number[];
  confidence: ScanConfidence;
  polygon_corners?: Point3[];
};
export type HouseObject = HouseSurface & { category: string };
export type HouseRoom = {
  id: string;
  name: string;
  walls: HouseSurface[];
  doors: HouseSurface[];
  windows: HouseSurface[];
  openings: HouseSurface[];
  floors: HouseSurface[];
  objects: HouseObject[];
};
export type HouseCapture = {
  schema_version: 1;
  capture_id: string;
  source: 'apple_roomplan' | 'manual';
  captured_at: string;
  rooms: HouseRoom[];
};
export type HouseScanSummary = {
  id: string;
  title: string;
  capture_id: string;
  source: 'apple_roomplan' | 'manual';
  captured_at: string;
  created_at: string;
  updated_at: string;
  revision: number;
  room_count: number;
  wall_count: number;
  verified_wall_count: number;
};
export type RoomLabel = { room_id: string; name: string };
export type VerifiedWallMeasurement = {
  room_id: string;
  wall_id: string;
  length_m: number;
  verified_at: string;
  source: 'user_verified';
};
export type HouseScan = HouseScanSummary & {
  capture: HouseCapture;
  room_labels: RoomLabel[];
  wall_measurements: VerifiedWallMeasurement[];
};
export type HouseScanPatch = {
  revision: number;
  title?: string;
  room_labels?: RoomLabel[];
  wall_measurements?: { room_id: string; wall_id: string; length_m: number | null }[];
};
export type ManualRoomInput = {
  name: string; length_m: number; width_m: number; height_m: number; doors: number; windows: number;
};
