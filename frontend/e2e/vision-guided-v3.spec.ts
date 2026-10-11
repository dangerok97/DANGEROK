/** Actual built UI + disposable Mongo; synthetic camera/recognition, not an iPhone sensor test. */
import {test,expect,type Page} from '@playwright/test';
import {mkdirSync} from 'node:fs';
mkdirSync('../.vision-evidence',{recursive:true});
async function session(page:Page){await page.addInitScript(()=>localStorage.setItem('ora_auth_token',JSON.stringify('vision-test-alice')));}
async function open(page:Page){await session(page);await page.goto('/vision-xray');await page.getByTestId('vision-catalog-toggle').click();await page.getByTestId('vision-catalog-remote_control').click();await expect(page.getByTestId('vision-how-it-works')).toBeVisible();}
async function camera(page:Page){
 await page.addInitScript(()=>{
  const state={blank:false,opens:0,stream:null as MediaStream|null};(window as any).__v3cam=state;
  const devices={getUserMedia:async()=>{
   state.opens++;const c=document.createElement('canvas');c.width=640;c.height=480;const x=c.getContext('2d')!;
   const draw=()=>{x.fillStyle='#b1a592';x.fillRect(0,0,640,480);if(!state.blank){x.fillStyle='#222a2c';x.fillRect(260,70,110,340);for(let r=0;r<10;r++)for(let j=0;j<3;j++){x.fillStyle=r%2?'#d1d5ce':'#70858c';x.fillRect(273+j*30,85+r*30,12,12);}}};
   draw();setInterval(draw,40);state.stream=c.captureStream(24);return state.stream;
  }};Object.defineProperty(navigator,'mediaDevices',{configurable:true,get:()=>devices});
 });
}

test('tour links the actual parts, pauses, advances, discloses sources and restores focus',async({page},info)=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));await open(page);
 await page.getByTestId('vision-part-pcb').click();await expect(page.getByTestId('vision-part-detail')).toBeVisible();
 await page.getByTestId('vision-how-it-works').click();
 const scene=page.getByTestId('vision-scene');await expect(scene).toHaveAttribute('data-tour-step','0');
 await expect(page.getByTestId('vision-part-detail')).toHaveCount(0);
 await page.getByTestId('vision-tour-play').click();await expect(page.getByTestId('vision-tour-play')).toHaveText('Riprendi');
 const phase=await scene.getAttribute('data-tour-phase');await page.waitForTimeout(300);await expect(scene).toHaveAttribute('data-tour-phase',phase!);
 await page.getByTestId('vision-tour-next').click();await expect(scene).toHaveAttribute('data-tour-step','1');
 await expect(page.getByTestId('vision-tour')).toContainText('Il tasto diventa un comando');
 await page.screenshot({path:'../.vision-evidence/vision-v3-tour-'+info.project.name+'.png',fullPage:true});
 await page.getByTestId('vision-tour-sources').click();await expect(page.locator('.vx-tour-sources a')).toHaveCount(2);
 await page.getByTestId('vision-tour-close').click();await expect(scene).toHaveAttribute('data-tour-step','');
 await expect(scene).toHaveAttribute('data-focused-part','pcb');await expect(page.getByTestId('vision-part-detail')).toBeVisible();
 expect(errors).toEqual([]);
});

test('all five reviewed families have bounded manual paths with reduced motion',async({page})=>{
 await page.emulateMedia({reducedMotion:'reduce'});await open(page);
 for(const family of ['remote_control','click_pen','water_bottle','computer_mouse','flashlight']){
  await page.getByTestId('vision-catalog-toggle').click();await page.getByTestId('vision-catalog-'+family).click();
  await page.getByTestId('vision-how-it-works').click();await expect(page.getByTestId('vision-tour-play')).toHaveText('Riprendi');
  for(let step=0;step<3;step++){
   await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-tour-step',String(step));
   await expect(page.getByTestId('vision-tour')).toContainText('PERCORSO DIDATTICO');
   if(step<2)await page.getByTestId('vision-tour-next').click();
  }
  await expect(page.getByTestId('vision-tour-next')).toBeDisabled();await page.getByTestId('vision-tour-close').click();
 }
});

test('acquisition emerges near the target, remains after removal and X cancels tour without reopening video',async({page,browserName},info)=>{
 test.skip(browserName==='webkit','Synthetic captureStream is not a physical WebKit camera test.');
 await session(page);await camera(page);const scans:string[]=[];
 page.on('request',r=>{if(r.url().endsWith('/api/vision-xray/scan'))scans.push(r.url());});
 await page.goto('/vision-xray');await page.getByTestId('vision-open-camera').click();
 const scene=page.getByTestId('vision-scene');
 await expect(scene).toHaveAttribute('data-arrival','from-object');
 await page.screenshot({path:'../.vision-evidence/vision-v3-arrival-'+info.project.name+'.png',fullPage:true});
 await expect(scene).toHaveAttribute('data-arrival','complete');
 await page.getByTestId('vision-how-it-works').click();await page.evaluate(()=>{(window as any).__v3cam.blank=true;});
 await page.waitForTimeout(18_500);await expect(page.getByTestId('vision-tour-play')).toHaveText('Rivedi');
 await expect(scene).toHaveAttribute('data-part-count','8');expect(scans).toHaveLength(1);
 expect(await page.getByTestId('vision-camera-video').evaluate((v:HTMLVideoElement)=>v.paused)).toBe(false);
 await page.getByTestId('vision-close-model').click();await expect(page.getByTestId('vision-tour')).toHaveCount(0);
 await expect.poll(()=>scans.length).toBeGreaterThan(1);expect(await page.evaluate(()=>(window as any).__v3cam.opens)).toBe(1);
 await page.getByTestId('vision-stop-camera').click();
 expect(await page.evaluate(()=>(window as any).__v3cam.stream.getTracks().every((t:MediaStreamTrack)=>t.readyState==='ended'))).toBe(true);
});

test('short and landscape screens keep both close controls and tour text reachable',async({page})=>{
 await page.setViewportSize({width:390,height:640});await open(page);await page.getByTestId('vision-how-it-works').click();
 for(const viewport of [{width:390,height:640},{width:844,height:390}]){
  await page.setViewportSize(viewport);await page.waitForTimeout(150);
  for(const id of ['vision-close-model','vision-tour-close','vision-tour-play']){
   const b=await page.getByTestId(id).boundingBox();expect(b!.x).toBeGreaterThanOrEqual(0);expect(b!.y).toBeGreaterThanOrEqual(0);expect(b!.y+b!.height).toBeLessThanOrEqual(viewport.height);
  }
 }
});
