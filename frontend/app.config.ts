import type { ConfigContext, ExpoConfig } from 'expo/config';
import appJson from './app.json';

const base = appJson.expo as ExpoConfig;

function iosGoogleUrlScheme(clientId: string): string | null {
  const suffix = '.apps.googleusercontent.com';
  if (!clientId.endsWith(suffix)) return null;
  const identifier = clientId.slice(0, -suffix.length).trim();
  return identifier ? `com.googleusercontent.apps.${identifier}` : null;
}

export default ({ config }: ConfigContext): ExpoConfig => {
  const iosClientId = (process.env.EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID || '').trim();
  const iosUrlScheme = iosGoogleUrlScheme(iosClientId);
  const plugins = [...(base.plugins || [])];

  // The native plugin requires the real reversed iOS client ID. Keeping it
  // conditional lets web/email builds remain valid when Google is not configured.
  if (iosUrlScheme) {
    plugins.push([
      '@react-native-google-signin/google-signin',
      { iosUrlScheme },
    ]);
  }

  return {
    ...base,
    ...config,
    ios: { ...base.ios, ...config.ios },
    android: { ...base.android, ...config.android },
    web: { ...base.web, ...config.web },
    plugins,
  };
};
