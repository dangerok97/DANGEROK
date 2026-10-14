import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('./AnatomyExplorer.web.tsx',import.meta.url),'utf8');
test('camera-person anatomy never renders a schematic human, including on failure',()=>{
 assert.doesNotMatch(source,/import.*AnatomyVolume/);
 assert.doesNotMatch(source,/<AnatomyVolume\b/);
 assert.doesNotMatch(source,/\bsilhouettePath\b/);
 assert.doesNotMatch(source,/vx-anatomy-shell/);
 assert.match(source,/BodyParts3D/);
 assert.doesNotMatch(source,/vx-target-corner|vision-anatomy-preview/);
 assert.match(source,/&study=1/);
 assert.match(source,/vision-bp3d-unavailable/);
 assert.match(source,/vision-bp3d-retry/);
});
