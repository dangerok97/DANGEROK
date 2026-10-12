/** Real built UI + real Mongo catalog. Video/auth/recognition are CI fixtures, not live AI claims. */
import { test, expect, type Page } from '@playwright/test';
import { mkdirSync } from 'node:fs';
mkdirSync('../.vision-evidence',{recursive:true});

async function session(page: Page) {
  await page.addInitScript(() => { localStorage.setItem('ora_auth_token',JSON.stringify('vision-test-alice')); });
}
async function virtualCamera(page: Page) {
  await page.addInitScript(() => {
    const state:any={offset:0,blank:false,frames:0,stream:null,openings:0};
    (window as any).__visionFixture=state;
    const getUserMedia=async()=>{
      state.openings++;
      const c=document.createElement('canvas');c.width=640;c.height=480;
      const ctx=c.getContext('2d')!;
      const draw=()=>{
        state.frames++;ctx.fillStyle='#b1a592';ctx.fillRect(0,0,640,480);
        if(!state.blank){
          const x=260+state.offset;
          ctx.fillStyle='#222a2c';ctx.beginPath();ctx.roundRect(x,70,110,340,22);ctx.fill();
          ctx.strokeStyle='#535e60';ctx.lineWidth=3;ctx.stroke();
          ctx.fillStyle='#b98764';ctx.beginPath();ctx.arc(x+55,99,12,0,Math.PI*2);ctx.fill();
          for(let r=0;r<8;r++)for(let j=0;j<3;j++){ctx.fillStyle=r%2?'#d1d5ce':'#70858c';ctx.beginPath();ctx.arc(x+24+j*31,137+r*30,7,0,Math.PI*2);ctx.fill();}
        }
        ctx.fillStyle='#495d62';ctx.fillRect(20,440,state.frames%100,9);
      };draw();setInterval(draw,40);
      state.stream=c.captureStream(24);return state.stream;
    };
    const devices={getUserMedia};
    Object.defineProperty(navigator,'mediaDevices',{configurable:true,get:()=>devices});
  });
}

test('catalog model is rendered, every part is selectable and reload reuses the version',async({page},info)=>{
  await session(page);await page.goto('/vision-xray');
  await expect(page.getByTestId('vision-live-explorer')).toBeVisible();
  await expect(page.getByRole('checkbox')).toHaveCount(0);
  await expect(page.getByTestId('vision-catalog-policy')).toContainText('automaticamente');
  await page.getByTestId('vision-catalog-toggle').click();
  await expect(page.getByTestId('vision-catalog-remote_control')).toBeVisible();
  await page.getByTestId('vision-catalog-remote_control').click();
  await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-part-count','8');
  await expect(page.getByTestId('vision-status')).toContainText('Anteprima catalogo');
  for(const key of ['front_shell','keypad','pcb','emitter','rear_shell','battery_a','battery_b','cover']){
    await page.getByTestId('vision-part-'+key).click();
    await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-selected-part',key);
  }
  await page.getByTestId('vision-part-pcb').click();
  await expect(page.getByTestId('vision-part-detail')).toContainText('Scheda elettronica');
  await page.screenshot({path:'../.vision-evidence/vision-catalog-'+info.project.name+'.png',fullPage:true});
  const headers={Authorization:'Bearer vision-test-alice'};
  const before=await (await page.request.get('/api/vision-xray/catalog',{headers})).json();
  const remote=before.models.find((m:any)=>m.canonical_key==='remote_control');
  await page.reload();await page.getByTestId('vision-catalog-toggle').click();await page.getByTestId('vision-catalog-remote_control').click();
  const after=await (await page.request.get('/api/vision-xray/catalog/'+remote.model_id,{headers})).json();
  expect(after.version_id).toBe(remote.version_id);expect(after.cache_hit).toBe(true);expect(after.generation_used).toBe(false);
});

test('held diagram survives loss, remains interactive, X restarts scanning without reopening camera',async({page,browserName},info)=>{
  test.skip(browserName==='webkit','Real iPhone camera validation remains a separate device test.');
  await session(page);await virtualCamera(page);
  const scans:any[]=[];
  page.on('request',r=>{if(r.url().endsWith('/api/vision-xray/scan'))scans.push(r.postDataJSON());});
  await page.goto('/vision-xray');
  await page.getByTestId('vision-open-camera').click();
  await expect.poll(()=>page.getByTestId('vision-camera-video').evaluate((v:HTMLVideoElement)=>v.readyState)).toBeGreaterThanOrEqual(2);
  await expect(page.getByTestId('vision-status')).toContainText('Riconosco');
  await expect(page.getByRole('checkbox')).toHaveCount(0);
  const start=await page.getByTestId('vision-camera-video').evaluate((v:HTMLVideoElement)=>v.currentTime);
  await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-part-count','8');
  await page.waitForTimeout(800);
  const state=await page.getByTestId('vision-camera-video').evaluate((v:HTMLVideoElement)=>({time:v.currentTime,paused:v.paused,tracks:(v.srcObject as MediaStream).getTracks().map(t=>t.readyState)}));
  expect(state.time).toBeGreaterThan(start+.3);expect(state.paused).toBe(false);expect(state.tracks).toEqual(['live']);
  await page.getByTestId('vision-part-pcb').click();await expect(page.getByTestId('vision-part-detail')).toContainText('Scheda elettronica');
  await page.screenshot({path:'../.vision-evidence/vision-live-'+info.project.name+'.png',fullPage:true});
  await page.evaluate(()=>{(window as any).__visionFixture.offset=8;});
  await page.waitForTimeout(400);await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-part-count','8');
  await page.getByTestId('vision-toggle-explode').click();await expect(page.getByTestId('vision-toggle-explode')).toHaveText('Scomponi');
  await page.getByTestId('vision-toggle-explode').click();
  await page.evaluate(()=>{(window as any).__visionFixture.blank=true;});
  // Exceed both old 12s and 15s automatic scan thresholds with the object absent.
  await page.waitForTimeout(17_000);
  await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-part-count','8');
  await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-scene-state','held');
  await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-selected-part','pcb');
  await expect(page.getByTestId('vision-status')).toContainText('Schema fissato');
  expect(scans).toHaveLength(1);expect(scans[0]).not.toHaveProperty('contribute');
  await expect(page.getByTestId('vision-retry')).toHaveCount(0);
  await page.getByTestId('vision-part-battery_a').click();
  await expect(page.getByTestId('vision-part-detail')).toContainText('Prima pila');
  await page.getByTestId('vision-toggle-explode').click();
  await expect(page.getByTestId('vision-toggle-explode')).toHaveText('Scomponi');
  await page.getByTestId('vision-toggle-explode').click();
  await page.screenshot({path:'../.vision-evidence/vision-held-without-object-'+info.project.name+'.png',fullPage:true});
  const close=page.getByTestId('vision-close-model');
  await expect(close).toBeVisible();
  const size=await close.boundingBox();expect(size!.width).toBeGreaterThanOrEqual(44);expect(size!.height).toBeGreaterThanOrEqual(44);
  await page.evaluate(()=>{(window as any).__visionFixture.blank=false;});
  await close.click();
  await expect.poll(()=>scans.length).toBe(2);
  await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-part-count','8');
  expect(await page.evaluate(()=>(window as any).__visionFixture.openings)).toBe(1);
  expect(await page.getByTestId('vision-camera-video').evaluate((v:HTMLVideoElement)=>(v.srcObject as MediaStream).getTracks()[0].readyState)).toBe('live');
  await page.getByTestId('vision-stop-camera').click();
  expect(await page.evaluate(()=>(window as any).__visionFixture.stream.getTracks().map((t:MediaStreamTrack)=>t.readyState))).toEqual(['ended']);
  await expect(page.getByTestId('vision-open-camera')).toBeVisible();
});

test('denied camera permission is explained without a fake live state',async({page})=>{
  await session(page);
  await page.addInitScript(()=>{
    const devices={getUserMedia:async()=>{
      (window as any).__deniedCameraInvoked=true;
      throw new DOMException('Denied','NotAllowedError');
    }};
    Object.defineProperty(navigator,'mediaDevices',{configurable:true,get:()=>devices});
  });
  await page.goto('/vision-xray');await page.getByTestId('vision-open-camera').click();
  await expect.poll(()=>page.evaluate(()=>(window as any).__deniedCameraInvoked)).toBe(true);
  await expect(page.getByTestId('vision-error')).toContainText('Permesso negato');
  expect(await page.getByTestId('vision-camera-video').evaluate((v:HTMLVideoElement)=>v.srcObject)).toBeNull();
});


test('anatomy atlas uses same live camera, switchable levels and a same-stream X',async({page,browserName})=>{
  test.skip(browserName==='webkit','Physical-device camera controls are checked separately');
  await session(page);await virtualCamera(page);await page.goto('/vision-xray');
  await page.getByTestId('vision-open-camera').click();
  await expect(page.getByTestId('vision-open-anatomy')).toBeVisible();
  const initialTime=await page.getByTestId('vision-camera-video').evaluate((v:HTMLVideoElement)=>v.currentTime);
  await page.getByTestId('vision-open-anatomy').click();
  await expect(page.getByTestId('vision-anatomy')).toBeVisible();
  await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-scene-state','anatomy');
  await page.getByTestId('vision-anatomy-layer-muscles').click();
  await page.getByTestId('vision-anatomy-select-pectorals').click();
  await expect(page.getByTestId('vision-anatomy-description')).toContainText('movimenti delle braccia');
  await page.getByTestId('vision-anatomy-layer-organs').click();
  await page.getByTestId('vision-anatomy-part-heart').click();
  await expect(page.getByTestId('vision-anatomy-description')).toContainText('Pompa il sangue');
  await page.getByTestId('vision-anatomy-layer-reproductive').click();
  await expect(page.getByTestId('vision-anatomy-part-uterus')).toHaveCount(0);
  await page.getByTestId('vision-anatomy-variant-female').click();
  await expect(page.getByTestId('vision-anatomy-part-uterus')).toHaveCount(1);
  await page.getByTestId('vision-anatomy-variant-male').click();
  await expect(page.getByTestId('vision-anatomy-part-prostate')).toHaveCount(1);
  await expect(page.getByTestId('vision-anatomy-part-uterus')).toHaveCount(0);
  const afterTime=await page.getByTestId('vision-camera-video').evaluate((v:HTMLVideoElement)=>v.currentTime);
  expect(afterTime).toBeGreaterThan(initialTime);
  await expect(page.getByTestId('vision-anatomy')).toContainText('non vede sotto la pelle');
  await page.getByTestId('vision-anatomy-close').click();
  await expect(page.getByTestId('vision-anatomy')).toHaveCount(0);
  await expect(page.getByTestId('vision-camera-video')).toBeVisible();
  expect(await page.evaluate(()=>(window as any).__visionFixture.openings)).toBe(1);
});


test('anatomy is discoverable from the first screen, remains visible during live camera and X resets',async({page,browserName})=>{
 test.skip(browserName==='webkit','Video stream exercised on Chromium; WebKit camera still needs physical-device checks');
 await session(page); await virtualCamera(page); await page.goto('/vision-xray');
 const nav=page.getByTestId('vision-anatomy-nav');
 await expect(nav).toBeVisible();
 await expect(nav).toHaveText('Anatomia');
 await page.getByTestId('vision-anatomy-welcome').click();
 await expect(page.getByTestId('vision-anatomy')).toBeVisible();
 await expect(nav).toHaveAttribute('aria-pressed','true');
 const video=page.getByTestId('vision-camera-video');
 expect(await video.evaluate((v:HTMLVideoElement)=>(v.srcObject as MediaStream).getVideoTracks()[0].readyState)).toBe('live');
 const before=await video.evaluate((v:HTMLVideoElement)=>v.currentTime);
 await page.getByTestId('vision-anatomy-layer-bones').click();
 await page.getByTestId('vision-anatomy-select-skull').click();
 await expect(page.getByTestId('vision-anatomy-description')).toContainText('Protegge');
 const after=await video.evaluate((v:HTMLVideoElement)=>v.currentTime);
 expect(after).toBeGreaterThan(before);
 await page.getByTestId('vision-anatomy-close').click();
 await expect(page.getByTestId('vision-anatomy')).toHaveCount(0);
 await expect(nav).toBeVisible();
 await expect(nav).toHaveAttribute('aria-pressed','false');
 expect(await page.evaluate(()=>(window as any).__visionFixture.openings)).toBe(1);
 await nav.click();
 await expect(page.getByTestId('vision-anatomy')).toBeVisible();
});

test('anatomy remains discoverable after an object is displayed',async({page})=>{
 await session(page); await page.goto('/vision-xray');
 await page.getByTestId('vision-catalog-toggle').click();
 await page.getByTestId('vision-catalog-remote_control').click();
 await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-part-count','8');
 await expect(page.getByTestId('vision-anatomy-nav')).toBeVisible();
 await page.getByTestId('vision-anatomy-nav').click();
 await expect(page.getByTestId('vision-anatomy')).toBeVisible();
 await expect(page.getByTestId('vision-part-pcb')).toHaveCount(0);
});
