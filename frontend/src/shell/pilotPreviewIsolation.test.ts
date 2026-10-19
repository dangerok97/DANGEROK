/** Guard against accidental production data access from the experimental web preview. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {join} from 'node:path';
const root = join(process.cwd(), 'frontend');
const docker = readFileSync(join(root, 'Dockerfile.pilot'), 'utf8');
const conf = readFileSync(join(root, 'nginx.pilot.conf'), 'utf8');
const script = readFileSync(join(root, 'pilot-start.sh'), 'utf8');
const url = readFileSync(join(root, 'src/api/client.ts'), 'utf8');

assert.match(docker, /ENV EXPO_PUBLIC_BACKEND_URL=same-origin/);
assert.doesNotMatch(docker, /EXPO_PUBLIC_BACKEND_URL=https?:\/\//);
assert.doesNotMatch(docker, /ora-backend-production/i);
assert.match(docker, /COPY nginx\.pilot\.conf/);
assert.match(docker, /ENTRYPOINT.*pilot-start/);
assert.match(url, /fromEnv === 'same-origin'/);
assert.match(conf, /proxy_pass http:\/\/pilot-backend-350\.railway\.internal:8080/);
assert.doesNotMatch(conf, /ora-backend-production|ora-web-production/i);
assert.match(conf, /location \^~ \/api\/ \{\s*if \(\$pilot_auth_ok = 0\) \{ return 403; \}/);
assert.match(conf, /location \/ \{\s*if \(\$pilot_auth_ok = 0\) \{ return 403; \}/);
assert.match(conf, /location = \/pilot-unlock \{\s*auth_basic/);
assert.match(conf, /HttpOnly; Secure; SameSite=Strict/);
assert.match(conf, /map_hash_bucket_size 128;/);
assert.match(script, /PILOT_BASIC_AUTH_PASSWORD:\?Missing/);
assert.match(script, /PILOT_COOKIE_TOKEN:\?Missing/);
assert.match(script, /htpasswd /);
assert.match(script, /sed "s#__PILOT_COOKIE_TOKEN__/);
console.log('Pilot preview isolation checks passed');
