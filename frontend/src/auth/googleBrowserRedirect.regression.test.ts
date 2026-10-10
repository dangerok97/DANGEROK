import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import {
  authorizedGoogleUrl, GOOGLE_BROWSER_PROOF_KEY, isIOSWebBrowser, googleBrowserFailure,
} from './googleBrowserRedirect.ts';

const here = path.dirname(fileURLToPath(import.meta.url));
const login = fs.readFileSync(path.join(here, '../../app/login.tsx'), 'utf8');
const done = fs.readFileSync(path.join(here, '../../app/google-auth-complete.tsx'), 'utf8');
const gate = fs.readFileSync(path.join(here, '../shell/AuthGate.tsx'), 'utf8');
const backend = fs.readFileSync(path.join(here, '../../../backend/social_auth/browser.py'), 'utf8');

test('iOS Safari and Chrome select the full-page Google redirect', () => {
  assert.equal(isIOSWebBrowser('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0) CriOS/129.0'), true);
  assert.equal(isIOSWebBrowser('Mozilla/5.0 (iPad; CPU OS 18_0) Version/18.0 Safari'), true);
  assert.equal(isIOSWebBrowser('Mozilla/5.0 (Linux; Android 16) Chrome/132'), false);
  assert.equal(isIOSWebBrowser('Mozilla/5.0 (Macintosh; Intel Mac OS X) Chrome/132'), false);
  assert.match(login, /webOnIOS \? \(/);
  assert.match(login, /login-google-browser-redirect/);
  assert.match(login, /handleGoogleBrowserRedirect/);
});

test('all provider URLs are constrained to the real Google authorization endpoint', () => {
  const good = 'https://accounts.google.com/o/oauth2/v2/auth?state=opaque&code_challenge=test';
  assert.equal(authorizedGoogleUrl(good), true);
  for (const url of [
    'https://accounts.google.com.evil.example/o/oauth2/v2/auth?state=x&code_challenge=y',
    'https://evil.example/o/oauth2/v2/auth?state=x&code_challenge=y',
    'http://accounts.google.com/o/oauth2/v2/auth?state=x&code_challenge=y',
    'javascript:alert(1)',
    'https://accounts.google.com/o/oauth2/v2/auth',
  ]) assert.equal(authorizedGoogleUrl(url), false, url);
});

test('completion fragment and tab proof are read once, without a JWT in URL', () => {
  assert.match(done, /window\.location\.hash/);
  assert.match(done, /window\.history\.replaceState/);
  assert.match(done, /window\.sessionStorage\.removeItem/);
  assert.match(done, /googleBrowserLoginComplete\(ticket, proof\)/);
  assert.match(done, /routeAfterAuth\(router, auth\.user\.user_id\)/);
  assert.match(gate, /'\/google-auth-complete'/);
  assert.match(backend, /return urlunsplit\(parts\._replace\(query="", fragment=urlencode\(params\)\)\)/);
  assert.ok(GOOGLE_BROWSER_PROOF_KEY.length > 12);
});

test('Google failure is visible and a missed iframe has an independent redirect', () => {
  assert.match(login, /login-google-loading/);
  assert.match(login, /login-google-redirect-fallback/);
  assert.match(login, /login-google-retry/);
  assert.match(googleBrowserFailure('account_link_required'), /Email/);
  assert.match(googleBrowserFailure('google_login_cancelled'), /annullato/);
});
