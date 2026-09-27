import type { SceneOptions } from './scene';
import type { PresenceNode } from './state';
export type CanvasProps = { options: SceneOptions; onUnavailable: () => void; onSelect: (node: PresenceNode | null) => void };
