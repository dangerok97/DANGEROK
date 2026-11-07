import React, { useEffect, useRef } from 'react';
import { createPresenceScene, type Scene } from './scene';
import { presencePalette } from '@/src/theme/presence';
import type { CanvasProps } from './types';

// ONE SCENE FOR THE LIFE OF THE CANVAS.
// 7/11 video: while ORA was reasoning the map collapsed to a single point and
// grew back again and again. The scene was created in an effect that depended
// on `onUnavailable`, which callers pass as an inline arrow: every render of
// the chat (each activity poll) destroyed the scene and built a new one, which
// replayed the entrance and lost focus, camera and births. Callbacks live in
// refs; the scene is built once per mounted canvas and only receives updates.
export function PresenceCanvas({ options, onUnavailable, onSelect }: CanvasProps) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const scene = useRef<Scene | null>(null);
  const latest = useRef(options);
  latest.current = options;
  const select = useRef(onSelect);
  select.current = onSelect;
  const unavailable = useRef(onUnavailable);
  unavailable.current = onUnavailable;
  useEffect(() => {
    try { if (canvas.current) scene.current = createPresenceScene(canvas.current, latest.current, presencePalette, { onSelect: node => select.current(node) }); }
    catch { unavailable.current(); }
    return () => { scene.current?.destroy(); scene.current = null; };
  }, []);
  useEffect(() => { scene.current?.update(options); }, [options]);
  return <canvas ref={canvas} aria-hidden="true" style={{ width: '100%', height: '100%', display: 'block', touchAction: 'none' }} />;
}
