/** A browser may offer a native handoff, never claim LiDAR capability from UA. */
export type HouseScanLaunch = {
  mode: 'native' | 'iphone-web' | 'unsupported';
  nativeUrl: string | null;
  installUrl: string | null;
  releaseReady: boolean;
};

export function safeIosInstallUrl(raw: string | undefined): string | null {
  if (!raw) return null;
  try {
    const url = new URL(raw.trim());
    if (url.protocol !== 'https:' || url.username || url.password || url.port) return null;
    if (url.hostname === 'testflight.apple.com' && /^\/join\/[A-Za-z0-9]+\/?$/.test(url.pathname)) return url.toString();
    if (url.hostname === 'apps.apple.com' && /\/id\d+\/?$/.test(url.pathname)) return url.toString();
  } catch { /* Missing or invalid release configuration is not an install link. */ }
  return null;
}

export function getHouseScanLaunch(platform: string, userAgent = '', maxTouchPoints = 0): HouseScanLaunch {
  const configuredUrl = safeIosInstallUrl(process.env.EXPO_PUBLIC_IOS_INSTALL_URL);
  const releaseReady = process.env.EXPO_PUBLIC_IOS_ROOMPLAN_READY === '1' && configuredUrl !== null;
  const appleMobile = /iPhone|iPad|iPod/i.test(userAgent)
    || (/Macintosh/i.test(userAgent) && maxTouchPoints > 1);
  return {
    mode: platform === 'ios' ? 'native' : platform === 'web' && appleMobile ? 'iphone-web' : 'unsupported',
    nativeUrl: platform === 'web' && appleMobile ? 'ora://casa?scan=1' : null,
    installUrl: releaseReady ? configuredUrl : null,
    releaseReady,
  };
}

export function getWebScanLaunch(userAgent: string, maxTouchPoints = 0): HouseScanLaunch {
  return getHouseScanLaunch('web', userAgent, maxTouchPoints);
}
