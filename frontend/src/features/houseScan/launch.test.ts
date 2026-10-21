import assert from 'node:assert/strict';
import { test } from 'node:test';
import { getHouseScanLaunch, safeIosInstallUrl } from './launch.ts';
import { safeNextTarget } from '../../shell/nextTarget.ts';

test('iPhone browsers offer a handoff without asserting sensor support', () => {
  const result = getHouseScanLaunch('web', 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)');
  assert.equal(result.mode, 'iphone-web');
  assert.equal(result.nativeUrl, 'ora://casa?scan=1');
  assert.equal(getHouseScanLaunch('web', 'Mozilla/5.0 Android').mode, 'unsupported');
  assert.equal(getHouseScanLaunch('web', 'Macintosh', 5).mode, 'iphone-web');
  assert.equal(getHouseScanLaunch('web', 'Macintosh', 0).mode, 'unsupported');
  assert.equal(getHouseScanLaunch('ios').mode, 'native');
});

test('distribution remains unavailable without a valid verified release link', () => {
  const oldReady = process.env.EXPO_PUBLIC_IOS_ROOMPLAN_READY;
  const oldUrl = process.env.EXPO_PUBLIC_IOS_INSTALL_URL;
  try {
    process.env.EXPO_PUBLIC_IOS_ROOMPLAN_READY = '1';
    process.env.EXPO_PUBLIC_IOS_INSTALL_URL = 'https://example.org/ipa';
    assert.equal(getHouseScanLaunch('web', 'iPhone').releaseReady, false);
    assert.equal(getHouseScanLaunch('web', 'iPhone').installUrl, null);
    process.env.EXPO_PUBLIC_IOS_INSTALL_URL = 'https://testflight.apple.com/join/AbCd1234';
    assert.equal(getHouseScanLaunch('web', 'iPhone').releaseReady, true);
    process.env.EXPO_PUBLIC_IOS_ROOMPLAN_READY = '0';
    assert.equal(getHouseScanLaunch('web', 'iPhone').installUrl, null);
  } finally {
    if (oldReady === undefined) delete process.env.EXPO_PUBLIC_IOS_ROOMPLAN_READY;
    else process.env.EXPO_PUBLIC_IOS_ROOMPLAN_READY = oldReady;
    if (oldUrl === undefined) delete process.env.EXPO_PUBLIC_IOS_INSTALL_URL;
    else process.env.EXPO_PUBLIC_IOS_INSTALL_URL = oldUrl;
  }
});

test('only real Apple distribution URL shapes can be presented', () => {
  assert.equal(safeIosInstallUrl('https://apps.apple.com/it/app/ora/id1234567'), 'https://apps.apple.com/it/app/ora/id1234567');
  for (const value of ['javascript:alert(1)', 'https://testflight.apple.com.evil.test/join/abc',
    'https://user@testflight.apple.com/join/abc', 'http://testflight.apple.com/join/abc',
    'https://testflight.apple.com/', 'https://apps.apple.com/it/app/ora', 'https://testflight.apple.com:8443/join/a']) {
    assert.equal(safeIosInstallUrl(value), null);
  }
});

test('scan destination survives sign-in without admitting external redirects', () => {
  assert.equal(safeNextTarget('/casa?scan=1'), '/casa?scan=1');
  assert.equal(safeNextTarget('ora://casa?scan=1'), null);
  assert.equal(safeNextTarget('//evil.test/casa?scan=1'), null);
  assert.equal(safeNextTarget('/casamalicious'), null);
});
