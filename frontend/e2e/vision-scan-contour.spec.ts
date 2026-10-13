/** End-to-end SCAN V1, with synthetic pixels and a real versioned object schema.
 * Not evidence of an arbitrary-background SAM model, LiDAR, or device AR. */
import {test,expect,type Page} from '@playwright/test';
const headers={Authorization:'Bearer vision-test-alice'};
const box=[.23,.20,.54,.65];
async function session(page:Page){
 await page.addInitScript(()=>{try{localStorage.setItem('ora_auth_token',JSON.stringify('vision-test-alice'));}catch{/* opaque iframe has no storage */}});
}
async function coloredHand(page:Page,highContrast=true):Promise<Buffer>{
 const bytes=await page.evaluate((contrasting:boolean)=>{
  const c=document.createElement('canvas');c.width=160;c.height=160;
  const ctx=c.getContext('2d')!;
  ctx.fillStyle='#edf0f2';ctx.fillRect(0,0,160,160);
  ctx.fillStyle=contrasting?'#244e85':'#edf0f2';
  ctx.fillRect(51,83,58,47);
  ctx.fillRect(53,49,10,43);
  ctx.fillRect(69,37,12,52);
  ctx.fillRect(87,42,11,48);
  ctx.fillRect(102,59,9,35);
  return Array.from(atob(c.toDataURL('image/png').split(',')[1]),b=>b.charCodeAt(0));
 },highContrast);
 return Buffer.from(bytes);
}
async function fakeAtlas(page:Page){
 await page.route('**/bodyparts3d/ora-integrated.json',route=>route.fulfill({
  status:200,contentType:'application/json',
  body:JSON.stringify({provider:'BodyParts3D',dataset_version:'4.0',reference:'adult male',
   model_is_person_specific:false,parts:2234,concepts:3432})
 }));
 await page.route('**/bodyparts3d/index.html?*',route=>route.fulfill({
  status:200,contentType:'text/html',body:'<!doctype html><meta charset="utf-8"><title>Real atlas waiting</title>'
 }));
}
test('human target: a contour follows captured fingers without resurrecting old anatomy',async({page})=>{
 await session(page);await fakeAtlas(page);
 await page.route('**/api/vision-xray/scan',route=>route.fulfill({
  status:200,contentType:'application/json',
  body:JSON.stringify({status:'anatomy',body_region:'hand',
   identification:{canonical_key:'human_anatomy',object_name:'Mano',confidence:'high',
    body_region:'hand',body_side:'right',bbox:box}})
 }));
 await page.goto('/vision-xray');
 await page.locator('input[type=file]').setInputFiles({name:'hand.png',mimeType:'image/png',buffer:await coloredHand(page)});
 await expect(page.getByTestId('vision-anatomy')).toHaveAttribute('data-region','hand');
 const outline=page.getByTestId('vision-scan-overlay');
 await expect(outline).toHaveAttribute('data-mode','pixels');
 const d=await outline.locator('path.is-pixel').getAttribute('d');
 expect((d?.match(/L/g)||[]).length).toBeGreaterThan(12);
 await expect(outline).toHaveAttribute('data-scan-style','cinematic-v2');
 await expect(outline.locator('.vx-hud-node-ring')).toHaveCount(9);
 await expect(outline.locator('.vx-hud-reticle')).toHaveCount(1);
 await expect(outline.locator('.vx-hud-sweep')).toHaveCount(1);
 await expect(outline.getByText('PROFILO ACQUISITO')).toBeVisible();
 await expect(outline).toHaveCSS('pointer-events','none');
 await expect(page.getByTestId('vision-anatomy-volume')).toHaveCount(0);
 await expect(page.locator('.vx-anatomy-shell')).toHaveCount(0);
 await expect(page.getByTestId('vision-bp3d-frame')).toBeVisible();
 await expect(page.getByTestId('vision-anatomy-close')).toBeVisible();
});
test('common object: detected photo gets real contour before held exploded model',async({page})=>{
 await session(page);
 const list=await (await page.request.get('/api/vision-xray/catalog',{headers})).json();
 const entry=list.models.find((m:any)=>m.canonical_key==='smartphone')||list.models[0];
 const real=(await (await page.request.get('/api/vision-xray/catalog/'+entry.model_id,{headers})).json());
 expect(real.manifest?.parts?.length).toBeGreaterThan(1);
 await page.route('**/api/vision-xray/scan',route=>route.fulfill({
  status:200,contentType:'application/json',
  body:JSON.stringify({...real,status:'family',
   identification:{canonical_key:entry.canonical_key,object_name:real.manifest.title,
    confidence:'high',bbox:box,uncertainty:''}})
 }));
 await page.goto('/vision-xray');
 await page.locator('input[type=file]').setInputFiles({name:'object.png',mimeType:'image/png',buffer:await coloredHand(page)});
 await expect(page.getByTestId('vision-close-model')).toBeVisible();
 await expect(page.getByTestId('vision-scan-overlay')).toHaveAttribute('data-mode','pixels');
 const outline=page.getByTestId('vision-scan-overlay');
 const d=await outline.locator('path.is-pixel').getAttribute('d');
 expect((d?.match(/L/g)||[]).length).toBeGreaterThan(12);
 await expect(outline).toHaveAttribute('data-scan-style','cinematic-v2');
 await expect(outline.locator('.vx-hud-node-ring')).toHaveCount(9);
 await expect(outline.locator('.vx-hud-reticle')).toHaveCount(1);
 await expect(outline.locator('.vx-hud-sweep')).toHaveCount(1);
 await expect(outline.getByText('PROFILO ACQUISITO')).toBeVisible();
 await expect(outline).toHaveCSS('pointer-events','none');
 await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-arrival',/from-object|complete/);
 await page.getByTestId('vision-part-'+real.manifest.parts[0].key).click();
 await expect(page.getByTestId('vision-part-detail')).toBeVisible();
});
test('flat scene refuses a fabricated contour and keeps visible estimated target area',async({page})=>{
 await session(page);await fakeAtlas(page);
 await page.route('**/api/vision-xray/scan',route=>route.fulfill({
  status:200,contentType:'application/json',
  body:JSON.stringify({status:'anatomy',body_region:'hand',
   identification:{canonical_key:'human_anatomy',confidence:'medium',
    body_region:'hand',body_side:'right',bbox:box}})
 }));
 await page.goto('/vision-xray');
 await page.locator('input[type=file]').setInputFiles({
  name:'flat.png',mimeType:'image/png',buffer:await coloredHand(page,false)
 });
 await expect(page.getByTestId('vision-anatomy')).toBeVisible();
 await expect(page.getByTestId('vision-scan-overlay')).toHaveCount(0);
 const marker=page.getByTestId('vision-anatomy-preview');
 await expect(marker).toBeVisible();
 await expect(marker.locator('.vx-target-corner')).toHaveCount(4);
 await expect(marker.locator('canvas,svg')).toHaveCount(0);
});
