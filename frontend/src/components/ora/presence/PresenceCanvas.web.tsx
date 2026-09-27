import React, { useEffect, useRef } from 'react';
import { createPresenceScene, type Scene } from './scene';
import { presencePalette } from '@/src/theme/presence';
import type { CanvasProps } from './types';

export function PresenceCanvas({ options, onUnavailable }: CanvasProps) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const scene = useRef<Scene | null>(null);
  const initial = useRef(options);
  useEffect(() => {
    try { if (canvas.current) scene.current = createPresenceScene(canvas.current, initial.current, presencePalette); }
    catch { onUnavailable(); }
    return () => { scene.current?.destroy(); scene.current = null; };
  }, [onUnavailable]);
  useEffect(() => { scene.current?.update(options); }, [options]);
  return <canvas ref={canvas} aria-hidden="true" style={{ width: '100%', height: '100%', display: 'block', touchAction: 'pan-y' }} />;
}
