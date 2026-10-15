import React, { useCallback, useEffect, useRef } from 'react';
import { readPresenceNode } from './state';
import type { CanvasProps } from './types';

function payload(options: CanvasProps['options']) {
  return {
    mode: options.mode,
    area: options.area,
    paused: options.paused,
    reduced: options.reduced,
    selectedIndex: options.selectedIndex,
    resetKey: options.resetKey,
    zoomOverride: options.zoomOverride,
    spotlightId: options.spotlightId,
    stars: (options.stars || []).map(star => ({
      id: star.id,
      area: star.area,
      kind: star.kind,
      tentative: !!star.tentative,
      temporary: !!star.temporary,
      complete: !!star.complete,
    })),
  };
}

/**
 * Web uses the already-bundled BodyParts3D/Three.js renderer instead of the
 * legacy 2D canvas illusion. The iframe is same-origin and receives geometry
 * identifiers only; personal statements never leave React.
 */
export function PresenceCanvas({ options, onUnavailable, onSelect }: CanvasProps) {
  const frame = useRef<HTMLIFrameElement>(null);
  const latest = useRef(options);
  const select = useRef(onSelect);
  const unavailable = useRef(onUnavailable);
  latest.current = options;
  select.current = onSelect;
  unavailable.current = onUnavailable;

  const send = useCallback(() => {
    frame.current?.contentWindow?.postMessage(
      { type: 'ora:brain-state', version: 1, options: payload(latest.current) },
      window.location.origin,
    );
  }, []);

  useEffect(() => {
    const receive = (event: MessageEvent) => {
      if (event.origin !== window.location.origin || event.source !== frame.current?.contentWindow) return;
      const message = event.data;
      if (!message || typeof message !== 'object') return;
      if (message.type === 'ora:brain-ready') {
        send();
        return;
      }
      if (message.type === 'ora:brain-error') {
        unavailable.current();
        return;
      }
      if (message.type !== 'ora:brain-select') return;
      if (message.node === null) {
        select.current(null);
        return;
      }
      const node = readPresenceNode(message.node, latest.current.stars);
      if (node) select.current(node);
    };
    window.addEventListener('message', receive);
    return () => window.removeEventListener('message', receive);
  }, [send]);

  useEffect(() => { send(); }, [options, send]);

  return (
    <iframe
      ref={frame}
      src="/bodyparts3d/?ora=brain"
      title="Cervello tridimensionale di ORA"
      data-testid="ora-presence-brain-frame"
      onLoad={send}
      onError={() => unavailable.current()}
      style={{ width: '100%', height: '100%', display: 'block', border: 0, background: 'transparent' }}
    />
  );
}
