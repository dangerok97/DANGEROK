import type { PresenceArea, PresenceMode, PresenceNode } from './state';
export type SceneOptions = { mode: PresenceMode; area: PresenceArea | null; paused: boolean; reduced: boolean; active: boolean; selectedIndex?: number | null; resetKey?: number };
export type Scene = { update(options: Partial<SceneOptions>): void; destroy(): void; snapshot(): {camera: {x:number;y:number;z:number;zoom:number};activeHub:number;points:number;edges:number;frame:number;mode:string} };
export function createPresenceScene(canvas: HTMLCanvasElement, initial: SceneOptions, palette: Record<string,string>, events?: {onSelect?: (node: PresenceNode | null) => void}): Scene;
