import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import {join,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
const dir=dirname(fileURLToPath(import.meta.url));
const here=(p)=>readFileSync(join(dir,p),'utf8');
test('Vision no longer imports or executes a second pixel scanner',()=>{
 const live=here('LiveExplorer.web.tsx');
 for(const token of ['ScanOutline','pixelScan(','extractPixelContour','projectPixelContour','scanCapture','scanContour','vx-scanning','vision-scan-overlay'])
  assert.equal(live.includes(token),false,'Unexpected scanner code: '+token);
 for(const path of ['ScanOutline.web.tsx','scanCinematicStyle.ts','pixelContour.ts'])
  assert.equal(existsSync(join(dir,path)),false,'Unused scanner module still shipped: '+path);
});
test('recognition and interactive catalog remain enabled',()=>{
 const live=here('LiveExplorer.web.tsx');
 assert.match(live,/catalogApi.scan\(/);
 assert.match(live,/new VisionPresentation/);
 assert.match(live,/vision-toggle-explode/);
 assert.match(live,/vision-part-detail/);
});
test('3D anatomy opens enlarged without a scanner reticle or alternate procedural human',()=>{
 const anatomy=here('AnatomyExplorer.web.tsx');
 assert.match(anatomy,/&study=1/);
 assert.doesNotMatch(anatomy,/hasPixelContour|vision-anatomy-preview|vx-target-corner|AnatomyVolume/);
 assert.match(anatomy,/bodyparts3d\/ora-integrated\.json/);
});
