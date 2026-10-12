/** Browser anatomy QA with a synthetic photo; not medical validation or a physical camera test. */
import {test,expect,type Page} from '@playwright/test';
import {mkdirSync} from 'node:fs';
mkdirSync('../.vision-evidence',{recursive:true});
async function launchAnatomy(page:Page){
 await page.addInitScript(()=>localStorage.setItem('ora_auth_token',JSON.stringify('vision-test-alice')));
 await page.route('**/api/vision-xray/scan',route=>route.fulfill({
  status:200,contentType:'application/json',
  body:JSON.stringify({status:'anatomy',body_region:'full_body',identification:{canonical_key:'human_anatomy',body_region:'full_body'}})
 }));
 await page.goto('/vision-xray');
 const pixels=await page.evaluate(()=>{
  const c=document.createElement('canvas');c.width=160;c.height=160;
  const ctx=c.getContext('2d')!;ctx.fillStyle='#ddd';ctx.fillRect(0,0,160,160);
  return Array.from(atob(c.toDataURL('image/jpeg').split(',')[1]),v=>v.charCodeAt(0));
 });
 await page.locator('input[type=file]').setInputFiles({name:'synthetic-atlas.jpg',mimeType:'image/jpeg',buffer:Buffer.from(pixels)});
 await expect(page.getByTestId('vision-anatomy')).toBeVisible();
}
test('a vascular anatomy layer is searchable and users can switch regions without new scan',async({page},info)=>{
 const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));
 let scans=0;page.on('request',request=>{if(request.url().endsWith('/api/vision-xray/scan'))scans++;});
 await launchAnatomy(page);
 await page.getByTestId('vision-anatomy-layer-vessels').click();
 await expect(page.getByTestId('vision-anatomy-select-aorta')).toBeVisible();
 await expect(page.getByTestId('vision-anatomy-select-carotid_arteries')).toBeVisible();
 await page.getByTestId('vision-anatomy-search').fill('carotidi');
 await expect(page.getByTestId('vision-anatomy-select-carotid_arteries')).toHaveCount(1);
 await expect(page.getByTestId('vision-anatomy-select-aorta')).toHaveCount(0);
 await page.getByTestId('vision-anatomy-region-torso').click();
 await expect(page.getByTestId('vision-anatomy-search')).toHaveValue('');
 await page.getByTestId('vision-anatomy-layer-organs').click();
 await expect(page.getByTestId('vision-anatomy-select-heart')).toBeVisible();
 await page.getByTestId('vision-anatomy-select-heart').click();
 await expect(page.getByTestId('vision-anatomy-description')).toContainText('Cuore');
 await page.screenshot({path:'../.vision-evidence/vision-anatomy-deep-'+info.project.name+'.png',fullPage:true});
 expect(scans).toBe(1);
 expect(errors).toEqual([]);
});
test('3D isolation, keyboard rotation and compact controls work on narrow screens',async({page},info)=>{
 await launchAnatomy(page);
 await page.getByTestId('vision-anatomy-region-torso').click();
 await page.getByTestId('vision-anatomy-layer-organs').click();
 await page.getByTestId('vision-anatomy-select-heart').click();
 const volume=page.getByTestId('vision-anatomy-volume');
 await expect(volume).toBeVisible();
 await expect.poll(async()=>Number(await volume.getAttribute('data-face-count'))).toBeGreaterThan(1);
 await page.evaluate(()=>{
  const element=document.querySelector('[data-testid=vision-anatomy-volume]')!;
  const event=(type:string,id:number,x:number,y:number)=>element.dispatchEvent(
   new PointerEvent(type,{bubbles:true,pointerId:id,pointerType:'touch',clientX:x,clientY:y}));
  event('pointerdown',41,100,200);event('pointerdown',42,160,200);
  event('pointermove',42,205,200);
  event('pointerup',42,205,200);event('pointerup',41,100,200);
 });
 await expect.poll(async()=>Number(await volume.getAttribute('data-zoom'))).toBeGreaterThan(1.2);

 await page.getByTestId('vision-anatomy-tools').click();
 await expect(page.getByTestId('vision-anatomy-isolate')).toBeVisible();
 await page.getByTestId('vision-anatomy-isolate').click();
 await expect(volume).toHaveAttribute('data-face-count','1');
 await page.getByTestId('vision-anatomy-explode').press('ArrowRight');
 const before=await volume.getAttribute('data-yaw');
 await volume.focus();await volume.press('ArrowRight');
 await expect.poll(async()=>volume.getAttribute('data-yaw')).not.toBe(before);
 await page.getByTestId('vision-anatomy-isolate').click();
 await expect.poll(async()=>Number(await volume.getAttribute('data-face-count'))).toBeGreaterThan(1);
 const orbit=await page.locator('.vx-anatomy-volume-controls').boundingBox();
 const zoomControls=await page.locator('.vx-anatomy-zoom').boundingBox();
 if(page.viewportSize()!.width<=650){
  expect(orbit).not.toBeNull();expect(zoomControls).not.toBeNull();
  expect(orbit!.y+orbit!.height).toBeLessThanOrEqual(zoomControls!.y);
 }
 const close=await page.getByTestId('vision-anatomy-close').boundingBox();
 const viewport=page.viewportSize()!;
 expect(close).not.toBeNull();
 expect(close!.x).toBeGreaterThanOrEqual(0);
 expect(close!.x+close!.width).toBeLessThanOrEqual(viewport.width);
 await page.screenshot({path:'../.vision-evidence/vision-anatomy-isolate-'+info.project.name+'.png',fullPage:true});
});


test('validated BodyParts3D geometry opens by default, stays sandboxed, and fallback needs no rescan',async({page})=>{
 let requests=0;
 page.on('request',r=>{if(r.url().endsWith('/api/vision-xray/scan'))requests++;});
 await page.route('**/bodyparts3d/ora-integrated.json',route=>route.fulfill({
  status:200,contentType:'application/json',body:JSON.stringify({
   provider:'BodyParts3D',dataset_version:'4.0',reference:'adult male',
   model_is_person_specific:false,parts:2234,concepts:3432
  })
 }));
 await page.route('**/bodyparts3d/index.html',route=>route.fulfill({
  status:200,contentType:'text/html',body:'<!doctype html><title>Isolated BodyParts3D test frame</title>'
 }));
 await launchAnatomy(page);
 const frame=page.getByTestId('vision-bp3d-frame');
 await expect(frame).toBeVisible();
 await expect(frame).toHaveAttribute('sandbox','allow-scripts allow-popups allow-popups-to-escape-sandbox');
 await expect(frame).toHaveAttribute('src',/ora=inline&lang=it&region=full_body&cx=/);
 await expect(page.getByTestId('vision-anatomy')).toHaveAttribute('data-visual-mode','camera-overlay');
 expect((await frame.getAttribute('sandbox'))).not.toContain('allow-same-origin');
 const fullScreen=page.getByTestId('vision-bp3d-fullscreen');
 await expect(fullScreen).toHaveAttribute('href','/bodyparts3d/index.html');
 await expect(fullScreen).toHaveAttribute('target','_blank');
 await expect(fullScreen).toHaveAttribute('rel','noopener noreferrer');
 await expect(fullScreen).toBeHidden(); // Person view must not become a separate full-screen page.
 await expect(page.getByTestId('vision-bp3d-toggle')).toHaveAttribute('aria-pressed','true');
 await expect(page.getByText('2.234 mesh')).toBeVisible();
 await page.getByTestId('vision-bp3d-fallback').click();
 await expect(frame).toHaveCount(0);
 await expect(page.getByTestId('vision-anatomy-layer-organs')).toBeVisible();
 await page.getByTestId('vision-bp3d-toggle').click();
 await expect(frame).toBeVisible();
 await expect(page.getByTestId('vision-anatomy-close')).toBeVisible();
 expect(requests).toBe(1);
});
test('mismatched or missing BodyParts3D provenance never hides the original ORA atlas',async({page})=>{
 await page.route('**/bodyparts3d/ora-integrated.json',route=>route.fulfill({
  status:200,contentType:'application/json',body:JSON.stringify({
   provider:'BodyParts3D',dataset_version:'4.0',reference:'adult female',
   model_is_person_specific:false,parts:2234,concepts:3432
  })
 }));
 await launchAnatomy(page);
 await expect(page.getByTestId('vision-bp3d-unavailable')).toBeVisible();
 await expect(page.getByTestId('vision-bp3d-toggle')).toBeDisabled();
 await expect(page.getByTestId('vision-anatomy-volume')).toBeVisible();
 await expect(page.getByTestId('vision-bp3d-frame')).toHaveCount(0);
});


test('anatomy appears only after person detection, not as a separate navigation section',async({page})=>{
 let scans=0;page.on('request',r=>{if(r.url().endsWith('/api/vision-xray/scan'))scans++;});
 await page.route('**/bodyparts3d/ora-integrated.json',route=>route.fulfill({
  status:200,contentType:'application/json',body:JSON.stringify({
   provider:'BodyParts3D',dataset_version:'4.0',reference:'adult male',
   model_is_person_specific:false,parts:2234,concepts:3432
  })
 }));
 await launchAnatomy(page);
 await expect(page.getByTestId('vision-open-human-atlas')).toHaveCount(0);
 await expect(page.getByTestId('vision-anatomy')).toHaveAttribute('data-visual-mode','camera-overlay');
 await expect(page.getByTestId('vision-bp3d-frame')).toHaveAttribute('src',/ora=inline&lang=it/);
 await page.getByTestId('vision-anatomy-close').click();
 await expect(page.getByTestId('vision-anatomy')).toHaveCount(0);
 expect(scans).toBe(1);
});

test('held person overlay keeps the real camera stream and X reuses it for the next target',async({page,browserName})=>{
 test.skip(browserName==='webkit','Synthetic captureStream is not a physical WebKit camera.');
 let scans=0;
 await page.route('**/api/vision-xray/scan',route=>{
  scans++;return route.fulfill({status:200,contentType:'application/json',
   body:JSON.stringify({status:'anatomy',body_region:'full_body',
     identification:{canonical_key:'human_anatomy',body_region:'full_body',bbox:[.25,.10,.5,.8]}})});
 });
 await page.route('**/bodyparts3d/ora-integrated.json',route=>route.fulfill({
  status:200,contentType:'application/json',
  body:JSON.stringify({provider:'BodyParts3D',dataset_version:'4.0',reference:'adult male',
    model_is_person_specific:false,parts:2234,concepts:3432})
 }));
 await page.route('**/bodyparts3d/index.html?*',route=>route.fulfill({
  status:200,contentType:'text/html',body:'<!doctype html><html lang="it"><title>Overlay didattico test</title><body style="background:transparent">Modello didattico</body></html>'
 }));
 await page.addInitScript(()=>{
  localStorage.setItem('ora_auth_token',JSON.stringify('vision-test-alice'));
  const state={opened:0,stream:null as MediaStream|null};
  (window as any).__personCam=state;
  Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{getUserMedia:async()=>{
   state.opened++;const canvas=document.createElement('canvas');canvas.width=640;canvas.height=480;
   const c=canvas.getContext('2d')!;c.fillStyle='#7c989e';c.fillRect(0,0,640,480);
   state.stream=canvas.captureStream(18);return state.stream;
  }}});
 });
 await page.goto('/vision-xray');
 await page.getByTestId('vision-open-camera').click();
 await expect(page.getByTestId('vision-anatomy')).toBeVisible({timeout:20000});
 await expect(page.getByTestId('vision-anatomy')).toHaveAttribute('data-visual-mode','camera-overlay');
 const frame=page.getByTestId('vision-bp3d-frame');
 await expect(frame).toHaveAttribute('src',/ora=inline&lang=it&region=full_body&cx=0.500/);
 await expect(page.getByTestId('vision-camera-video')).toBeVisible();
 await expect(page.getByTestId('vision-camera-video')).not.toHaveJSProperty('paused',true);
 const previous=scans;
 await page.waitForTimeout(1800);
 expect(scans).toBe(previous);
 await page.getByTestId('vision-anatomy-close').click();
 await expect(page.getByTestId('vision-anatomy')).toHaveCount(0);
 await expect.poll(()=>scans).toBeGreaterThan(previous);
 const opens=await page.evaluate(()=>(window as any).__personCam.opened);
 expect(opens).toBe(1);
 await page.getByTestId('vision-stop-camera').click();
 expect(await page.evaluate(()=>(window as any).__personCam.stream.getTracks().every((t:MediaStreamTrack)=>t.readyState==='ended'))).toBe(true);
});
