/** No-scanner Vision regression: built ORA UI, synthetic upload/auth and real
 * versioned seeded catalog. This is not a physical-camera validation. */
import {test,expect,type Page} from '@playwright/test';
const headers={Authorization:'Bearer vision-test-alice'};
async function session(page:Page){
 await page.addInitScript(()=>{try{
  localStorage.setItem('ora_auth_token',JSON.stringify('vision-test-alice'));
 }catch{/* an atlas sandbox cannot access localStorage */}});
}
async function still(page:Page){
 const bytes=await page.evaluate(()=>{
  const canvas=document.createElement('canvas');canvas.width=180;canvas.height=160;
  const ctx=canvas.getContext('2d')!;
  ctx.fillStyle='#e3eaf2';ctx.fillRect(0,0,180,160);
  ctx.fillStyle='#bc8a66';ctx.fillRect(44,57,82,76);
  for(let i=0;i<4;i++)ctx.fillRect(47+i*19,24+i%2*8,11,43);
  return Array.from(atob(canvas.toDataURL('image/png').split(',')[1]),x=>x.charCodeAt(0));
 });
 await page.locator('input[type=file]').setInputFiles({
  name:'visual-study.png',mimeType:'image/png',buffer:Buffer.from(bytes)});
}
async function fakeAtlas(page:Page){
 await page.route('**/bodyparts3d/ora-integrated.json',route=>route.fulfill({
  status:200,contentType:'application/json',
  body:JSON.stringify({provider:'BodyParts3D',dataset_version:'4.0',reference:'adult male',
   model_is_person_specific:false,parts:2234,concepts:3432})
 }));
 await page.route('**/bodyparts3d/index.html?*',route=>route.fulfill({
  status:200,contentType:'text/html',body:'<!doctype html><meta charset="utf-8"><title>Atlas reference test</title>'
 }));
}
test('human hand opens enlarged BodyParts3D study; no pixel scanner or fake skeleton',async({page})=>{
 await session(page);await fakeAtlas(page);
 await page.route('**/api/vision-xray/scan',route=>route.fulfill({
  status:200,contentType:'application/json',
  body:JSON.stringify({status:'anatomy',body_region:'hand',
   identification:{canonical_key:'human_anatomy',body_region:'hand',
    body_side:'right',bbox:[.24,.14,.53,.70],confidence:'high'}})
 }));
 await page.goto('/vision-xray');await still(page);
 const human=page.getByTestId('vision-anatomy');
 await expect(human).toHaveAttribute('data-region','hand');
 await expect(human).toHaveAttribute('data-display','study-first');
 const frame=page.getByTestId('vision-bp3d-frame');
 await expect(frame).toBeVisible();
 const url=new URL((await frame.getAttribute('src'))!,'https://ora.example');
 expect(url.searchParams.get('study')).toBe('1');
 expect(url.searchParams.get('region')).toBe('hand');
 await expect(page.getByTestId('vision-anatomy-volume')).toHaveCount(0);
 await expect(page.getByTestId('vision-scan-overlay')).toHaveCount(0);
 await expect(page.getByTestId('vision-anatomy-preview')).toHaveCount(0);
 await expect(page.locator('.vx-target-corner')).toHaveCount(0);
 await expect(page.getByTestId('vision-anatomy-close')).toBeVisible();
});
test('object catalog model remains interactive without extra image-segmentation overlay',async({page})=>{
 await session(page);
 const list=await (await page.request.get('/api/vision-xray/catalog',{headers})).json();
 const entry=list.models.find((m:any)=>m.canonical_key==='remote_control')||list.models[0];
 const model=await (await page.request.get('/api/vision-xray/catalog/'+entry.model_id,{headers})).json();
 await page.route('**/api/vision-xray/scan',route=>route.fulfill({
  status:200,contentType:'application/json',
  body:JSON.stringify({...model,status:'family',
   identification:{canonical_key:entry.canonical_key,object_name:model.manifest.title,
     confidence:'high',bbox:[.25,.15,.5,.7],uncertainty:''}})
 }));
 await page.goto('/vision-xray');await still(page);
 await expect(page.getByTestId('vision-close-model')).toBeVisible();
 await expect(page.getByTestId('vision-scan-overlay')).toHaveCount(0);
 await page.getByTestId('vision-part-'+model.manifest.parts[0].key).click();
 await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-selected-part',model.manifest.parts[0].key);
 await expect(page.getByTestId('vision-part-detail')).toBeVisible();
 await page.getByTestId('vision-zoom-in').click();
 await expect(page.getByTestId('vision-zoom-out')).toBeVisible();
 await page.getByTestId('vision-overview').click();
 await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-selected-part',model.manifest.parts[0].key);
});
test('no detector rectangle still displays honest enlarged anatomical reference',async({page})=>{
 await session(page);await fakeAtlas(page);
 await page.route('**/api/vision-xray/scan',route=>route.fulfill({
  status:200,contentType:'application/json',
  body:JSON.stringify({status:'anatomy',body_region:'forearm',
   identification:{canonical_key:'human_anatomy',body_region:'forearm',body_side:'left'}})
 }));
 await page.goto('/vision-xray');await still(page);
 await expect(page.getByTestId('vision-anatomy')).toHaveAttribute('data-region','forearm');
 const src=await page.getByTestId('vision-bp3d-frame').getAttribute('src');
 expect(src).toContain('study=1');
 expect(src).not.toContain('&bw=');
 await expect(page.getByTestId('vision-scan-overlay')).toHaveCount(0);
 await expect(page.getByTestId('vision-anatomy-preview')).toHaveCount(0);
});

test('crowded objects show readable exploded groups; each part remains selectable',async({page})=>{
 await session(page);
 await page.goto('/vision-xray');
 await page.getByTestId('vision-catalog-toggle').click();
 await page.getByTestId('vision-catalog-remote_control').click();
 const canvas=page.getByTestId('vision-scene');
 await expect(canvas).toHaveAttribute('data-part-count','8');
 const pager=page.getByTestId('vision-object-pager');
 await expect(pager).toBeVisible();
 await expect(pager).toHaveAttribute('data-pages','2');
 await expect(pager).toHaveAttribute('data-mode','paged');
 await expect.poll(()=>canvas.getAttribute('data-visible-part-count')).toBe('6');
 await expect(canvas).toHaveAttribute('data-visible-page','1');
 await page.getByTestId('vision-object-next-page').click();
 await expect(pager).toHaveAttribute('data-page','2');
 await expect.poll(()=>canvas.getAttribute('data-visible-part-count')).toBe('2');
 await expect(canvas).toHaveAttribute('data-visible-page','2');
 await page.getByTestId('vision-part-battery_b').click();
 await expect(page.getByTestId('vision-part-detail')).toBeVisible();
 await expect(canvas).toHaveAttribute('data-selected-part','battery_b');
 await expect(page.getByTestId('vision-object-pager')).toHaveCount(0);
 await page.getByTestId('vision-overview').click();
 await expect(page.getByTestId('vision-object-pager')).toHaveAttribute('data-page','2');
 await expect.poll(()=>canvas.getAttribute('data-visible-part-count')).toBe('2');
 await page.getByTestId('vision-object-all-toggle').click();
 await expect(pager).toHaveAttribute('data-mode','all');
 await expect.poll(()=>canvas.getAttribute('data-visible-part-count')).toBe('8');
 await page.getByTestId('vision-object-all-toggle').click();
 await expect(pager).toHaveAttribute('data-mode','paged');
 await expect.poll(()=>canvas.getAttribute('data-visible-part-count')).toBe('2');
 // A mobile viewport can still reach the controls without hiding the 3D stage.
 const stage=await page.getByTestId('vision-stage').boundingBox();
 const rect=await pager.boundingBox();
 expect(stage&&rect).toBeTruthy();
 expect(rect!.x).toBeGreaterThanOrEqual(stage!.x-1);
 expect(rect!.x+rect!.width).toBeLessThanOrEqual(stage!.x+stage!.width+1);
 expect(rect!.y).toBeGreaterThan(stage!.y);
 expect(rect!.y+rect!.height).toBeLessThanOrEqual(stage!.y+stage!.height+1);
 await expect(page.getByTestId('vision-close-model')).toBeVisible();
 await expect(page.getByTestId('vision-scan-overlay')).toHaveCount(0);
});
