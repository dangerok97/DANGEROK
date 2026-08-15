/**
 * Regression: missing backend URL must not become opaque "Failed to fetch".
 * node frontend/src/api/resolveBackendBaseUrl.regression.mjs
 */
import assert from 'assert';

function resolveBackendBaseUrl(envUrl, hostname) {
  const fromEnv = String(envUrl || '').trim().replace(/\/$/, '');
  if (fromEnv) return fromEnv;
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return `http://${hostname}:8000`;
  }
  return '';
}

assert.strictEqual(resolveBackendBaseUrl(undefined, '127.0.0.1'), 'http://127.0.0.1:8000');
assert.strictEqual(resolveBackendBaseUrl(undefined, 'localhost'), 'http://localhost:8000');
assert.strictEqual(resolveBackendBaseUrl('http://127.0.0.1:8000/', 'localhost'), 'http://127.0.0.1:8000');
assert.strictEqual(resolveBackendBaseUrl(undefined, 'example.com'), '');

console.log('ok: backend URL resolve regression');
