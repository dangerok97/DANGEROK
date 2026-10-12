import { Platform } from 'react-native';
import * as WebBrowser from 'expo-web-browser';

import {
  runConnectorOAuth,
  type ConnectorOAuthDestination,
  type ConnectorOAuthKind,
  type ConnectorOAuthPorts,
} from './connectorOAuth';

/** Uses the installed Expo auth session, including its Android Linking return. */
export function connectGoogleSource(
  kind: ConnectorOAuthKind,
  destination: ConnectorOAuthDestination,
  source: Pick<ConnectorOAuthPorts, 'start' | 'instances'>,
) {
  return runConnectorOAuth(kind, destination, {
    ...source,
    platform: Platform.OS === 'web' ? 'web' : 'native',
    webOrigin: typeof window !== 'undefined' ? window.location?.origin : undefined,
    openAuthSession: (url, returnUrl) => WebBrowser.openAuthSessionAsync(url, returnUrl),
    navigate: url => { window.location.assign(url); },
  });
}
