/** Real built UI + real Mongo catalog. Video/auth/recognition are CI fixtures, not live AI claims. */
import { test, expect, type Page } from '@playwright/test';
import { mkdirSync } from 'node:fs';
mkdirSync('../.vision-evidence',{recursive:true});

async function session(page: Page) {
  await page.addInitScript(() => { localStorage.setItem('ora_auth_token',JSON.stringify('vision-test-alice')); });
}
async function virtualCamera(page: Page) {
  await page.addInitScript(() => {
    const state:any={offset:0,blank:false,frames:0,stream:null};
    (window as any).__visionFixture=state;
    Object.defineProperty(navigator.mediaDevices,'getUserMedia',{configurable:true,value:async()=>{
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
        // This indicator changes on every frame, independently of the object.
        ctx.fillStyle='#495d62';ctx.fillRect(20,440,state.frames%100,9);
      };draw();setInterval(draw,40);
      state.stream=c.captureStream(24);return state.stream;
    }});
  });
}

test('catalog model is rendered, every part is selectable and reload reuses the version',async({page},info)=>{
  await session(page);await page.goto('/vision-xray');
  await expect(page.getByTestId('vision-live-explorer')).toBeVisible();
  await page.getByTestId('vision-catalog-toggle').click();
  await expect(page.getByTestId('vision-catalog-remote_control')).toBeVisible();
  await page.getByTestId('vision-catalog-remote_control').click();
  await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-part-count','8');
  await expect(page.getByTestId('vision-status')).toContainText('Anteprima catalogo');
  const parts=page.locator('[data-testid^="vision-part-"]').filter({hasNot:page.locator('h2')});
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

test('video remains live during analysis and exploded view, hides on loss, stops on command',async({page,browserName},info)=>{
  // WebKit's headless canvas capture is not a substitute for testing a real iPhone camera.
  test.skip(browserName==='webkit','Real iPhone camera validation remains a separate device test.');
  await session(page);await virtualCamera(page);await page.goto('/vision-xray');
  await page.getByTestId('vision-open-camera').click();
  await expect.poll(()=>page.getByTestId('vision-camera-video').evaluate((v:HTMLVideoElement)=>v.readyState)).toBeGreaterThanOrEqual(2);
  await expect(page.getByTestId('vision-status')).toContainText('Riconosco');
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
  await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-part-count','0');
  await expect(page.getByTestId('vision-status')).toContainText('Riaggancio');
  await page.getByTestId('vision-stop-camera').click();
  expect(await page.evaluate(()=>(window as any).__visionFixture.stream.getTracks().map((t:MediaStreamTrack)=>t.readyState))).toEqual(['ended']);
  await expect(page.getByTestId('vision-open-camera')).toBeVisible();
});

test('denied camera permission is explained without a fake live state',async({page})=>{
  await session(page);
  await page.addInitScript(()=>{Object.defineProperty(navigator.mediaDevices,'getUserMedia',{configurable:true,value:async()=>{throw new DOMException('Denied','NotAllowedError');}});});
  await page.goto('/vision-xray');await page.getByTestId('vision-open-camera').click();
  await expect(page.getByTestId('vision-error')).toContainText('Permesso negato');
  expect(await page.getByTestId('vision-camera-video').evaluate((v:HTMLVideoElement)=>v.srcObject)).toBeNull();
});
