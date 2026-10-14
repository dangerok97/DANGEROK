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

test('the camera no longer preloads anatomical files for ordinary-object recognition',()=>{
 const live=here('LiveExplorer.web.tsx');
 const open=live.indexOf('const openCamera=');
 const pick=live.indexOf('const pickPhoto=');
 const activate=live.indexOf('const activateAtlas=');
 assert.ok(open>=0&&pick>=0&&activate>=0);
 assert.doesNotMatch(live.slice(open,activate),/warmAnatomyReference\(/);
 assert.match(live.slice(activate,activate+450),/warmAnatomyReference\(/);
 assert.doesNotMatch(live,/const x=w\*\.26,y=h\*\.22/);
});
test('mobile atlas explosion pages fewer parts without inventing anatomy',()=>{
 const inline=readFileSync(join(dir,'../../scripts/ora-bodyparts3d-inline.tsx'),'utf8');
 assert.match(inline,/width<650\?8:width<1000\?10:12/);
 assert.match(inline,/eligiblePieces\.slice\(displayedPage\*pageSize,\(displayedPage\+1\)\*pageSize\)/);
 assert.match(inline,/data-testid=\{'ora-inline-piece-'\+part\.id\}/);
});
