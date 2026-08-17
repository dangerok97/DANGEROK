import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import {
  getGoogleAuthAvailability,
  googleAuthFailure,
} from './googleAuthAvailability.ts';

const here = path.dirname(fileURLToPath(import.meta.url));
const loginSource = fs.readFileSync(path.join(here, '../../app/login.tsx'), 'utf8');
const settingsSource = fs.readFileSync(path.join(here, '../../app/settings.tsx'), 'utf8');
const contextSource = fs.readFileSync(path.join(here, '../contexts/AuthContext.tsx'), 'utf8');
const webPath = path.join(here, 'googleAuth.web.ts');
const webSource = fs.readFileSync(webPath, 'utf8');
const nativeSource = fs.readFileSync(path.join(here, 'googleAuth.native.ts'), 'utf8');
const genericSource = fs.readFileSync(path.join(here, 'googleAuth.ts'), 'utf8');

const ids = {
  web: 'web.apps.googleusercontent.com',
  ios: 'ios.apps.googleusercontent.com',
  android: 'android.apps.googleusercontent.com',
};

test('A: web configurato è ready', () => {
  assert.equal(getGoogleAuthAvailability('web', ids).status, 'ready');
});

test('B/C/D/L: senza config Login resta renderizzabile, Google disabled, email disponibile', () => {
  assert.equal(
    getGoogleAuthAvailability('web', { web: '', ios: '', android: '' }).status,
    'missing_frontend_config',
  );
  assert.match(loginSource, /disabled=\{anyBusy \|\| !googleReady\}/);
  assert.match(loginSource, /login-email-button/);
  assert.doesNotMatch(loginSource, /useIdTokenAuthRequest|expo-auth-session\/providers\/google/);
});

test('E/G/H: failure di script/provider produce solo copy sicura', () => {
  const result = googleAuthFailure(
    new Error('Client Id property webClientId SECRET_INTERNAL_STACK'),
    'script_load_failed',
  );
  assert.equal(result.ok, false);
  assert.doesNotMatch(result.safeMessage, /webClientId|SECRET|stack/i);
  assert.match(webSource, /script_load_failed/);
});

test('F: cancellazione è distinta e non viene mostrata come errore', () => {
  const result = googleAuthFailure(new Error('popup dismissed'));
  assert.equal(result.cancelled, true);
  assert.equal(result.code, 'cancelled');
});

test('I: doppio click condivide la stessa operazione pending', () => {
  assert.match(webSource, /dataset\.oraGisButton === 'ready'/);
  assert.match(webSource, /buttonTimeout\.current/);
  assert.match(loginSource, /if \(busy\) return/);
});

test('J: Login e Settings usano lo stesso adapter', () => {
  assert.match(loginSource, /from '@\/src\/auth\/googleAuth'/);
  assert.match(settingsSource, /from '@\/src\/auth\/googleAuth'/);
  assert.doesNotMatch(settingsSource, /expo-auth-session\/providers\/google/);
});

test('K: storage JWT failure impedisce update user state', () => {
  const persistIndex = contextSource.indexOf('await authToken.set(token)');
  const userIndex = contextSource.indexOf('setUser(u)', persistIndex);
  assert.ok(persistIndex >= 0 && userIndex > persistIndex);
  assert.match(contextSource, /if \(!persisted\)/);
  assert.match(contextSource, /auth_storage_failed/);
});

test('M/N: GIS non riscrive localhost o 127.0.0.1', () => {
  assert.doesNotMatch(webSource, /location\.origin|replace\(.+localhost|replace\(.+127\.0\.0\.1/);
  assert.match(webSource, /https:\/\/accounts\.google\.com\/gsi\/client/);
});

test('P: loader GIS non resta pending con script già presente o fallito', () => {
  assert.match(webSource, /findGoogleIdentityServicesScript/);
  assert.match(webSource, /dataset\.oraGisState === 'loaded'/);
  assert.match(webSource, /dataset\.oraGisState === 'error'/);
  assert.match(webSource, /GIS_LOAD_TIMEOUT_MS/);
  assert.match(webSource, /setInterval\(succeedIfReady, GIS_READY_POLL_MS\)/);
  assert.match(webSource, /removeGoogleIdentityServicesScript\(script\)/);
  assert.match(webSource, /if \(gisLoadPromise\)/);
});

test('R: resolver separa in modo inequivocabile GIS Web e Google Sign-In native', () => {
  assert.equal(fs.existsSync(webPath), true);
  assert.match(webSource, /loadGoogleIdentityServices/);
  assert.match(webSource, /https:\/\/accounts\.google\.com\/gsi\/client/);
  assert.doesNotMatch(webSource, /@react-native-google-signin\/google-signin/);

  assert.match(nativeSource, /@react-native-google-signin\/google-signin/);
  assert.doesNotMatch(nativeSource, /loadGoogleIdentityServices|accounts\.google\.com\/gsi\/client/);

  assert.match(genericSource, /from '\.\/googleAuth\.web'/);
  assert.doesNotMatch(
    genericSource,
    /from '\.\/googleAuth\.native'|@react-native-google-signin/,
  );
});

test('S: il login Web usa il button flow GIS ufficiale e non One Tap', () => {
  assert.match(webSource, /google\.accounts\.id\.renderButton/);
  assert.match(webSource, /text: 'continue_with'/);
  assert.doesNotMatch(webSource, /google\.accounts\.id\.prompt\s*\(/);
  assert.match(loginSource, /renderGoogleButton/);
  assert.match(settingsSource, /renderGoogleButton/);
  assert.doesNotMatch(loginSource, /\.click\(\).*google|google.*\.click\(/i);
  assert.match(loginSource, /Platform\.OS === 'web' && googleButtonConfigured/);
  assert.doesNotMatch(loginSource, /Platform\.OS === 'web' && googleReady \?/);
  assert.match(webSource, /dataset\.oraGisButton === 'loading'/);
  assert.match(webSource, /if \(!gisInitialized\)/);
  assert.match(webSource, /gisCredentialHandler\?\.\(response\)/);
});
