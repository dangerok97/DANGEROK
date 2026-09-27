import React, { useEffect, useMemo, useRef } from 'react';
import { WebView } from 'react-native-webview';
import { sceneSource } from './sceneSource';
import { readPresenceNode } from './state';
import { presencePalette } from '@/src/theme/presence';
import type { CanvasProps } from './types';

/** Local scene only: no network, media, credentials or native action bridge. */
export function PresenceCanvas({ options, onUnavailable, onSelect }: CanvasProps) {
  const view = useRef<WebView>(null);
  const latest = useRef(options);
  latest.current = options;
  const source = useMemo(() => ({ html: `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'"><style>html,body,canvas{margin:0;width:100%;height:100%;overflow:hidden;background:${presencePalette.background}}canvas{display:block;touch-action:none}</style></head><body><canvas id="presence"></canvas><script>window.oraScene=(${sceneSource})(document.getElementById('presence'),${JSON.stringify({ ...latest.current, active: false })},${JSON.stringify(presencePalette)},{onSelect:function(node){window.ReactNativeWebView.postMessage(JSON.stringify({type:"select",node:node}));}});</script></body></html>` }), []);
  const sendOptions = () => view.current?.injectJavaScript(`window.oraScene&&window.oraScene.update(${JSON.stringify(latest.current)});true;`);
  useEffect(() => { sendOptions(); }, [options]);
  return <WebView ref={view} source={source} originWhitelist={['about:blank']} onShouldStartLoadWithRequest={request => request.url === 'about:blank'}
    onMessage={event => {
      try {
        const message = JSON.parse(event.nativeEvent.data);
        if (message.type !== 'select') return;
        if (message.node === null) onSelect(null);
        else { const node = readPresenceNode(message.node, latest.current.stars); if (node) onSelect(node); }
      } catch { /* Invalid bridge payloads never affect the conversation. */ }
    }}
    onLoadEnd={sendOptions} onError={onUnavailable} onContentProcessDidTerminate={onUnavailable}
    javaScriptEnabled domStorageEnabled={false} scrollEnabled={false} bounces={false}
    allowsInlineMediaPlayback={false} mediaPlaybackRequiresUserAction
    accessible={false} style={{ flex: 1, backgroundColor: presencePalette.background }} />;
}
