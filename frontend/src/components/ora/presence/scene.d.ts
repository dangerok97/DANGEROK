import type { PresenceArea, PresenceMode } from './state';
export type SceneOptions = { mode: PresenceMode; area: PresenceArea | null; paused: boolean; reduced: boolean; active: boolean };
export type Scene = { update(options: Partial<SceneOptions>): void; destroy(): void; snapshot(): {camera: {x:number;y:number;z:number;zoom:number};activeHub:number;points:number;edges:number;frame:number;mode:string} };
export function createPresenceScene(canvas: HTMLCanvasElement, initial: SceneOptions, palette: Record<string,string>): Scene;
