/** Built UI, real disposable Mongo. Camera/torch below are explicit test fixtures,
 * not a physical phone and not proof that Safari exposes a device torch. */
import {test,expect,type Page} from '@playwright/test';
import {mkdirSync} from 'node:fs';
mkdirSync('../.vision-evidence',{recursive:true});
const headers={Authorization:'Bearer vision-test-alice'};
async function session(page:Page){await page.addInitScript(()=>localStorage.setItem('ora_auth_token',JSON.stringify('vision-test-alice')));}
async function camera(page:Page,supported=true,ignore=false){
 await page.addInitScript(({supported,ignore})=>{
  const state:any={light:false,commands:[],opens:0,stream:null};(window as any).__cameraControls=state;
  const devices={getUserMedia:async()=>{
   state.opens++;
   const c=document.createElement('canvas');c.width=640;c.height=480;const ctx=c.getContext('2d')!;
   const draw=()=>{ctx.fillStyle='#b1a592';ctx.fillRect(0,0,640,480);ctx.fillStyle='#222a2c';ctx.fillRect(295,200,50,80);for(let i=0;i<5;i++){ctx.fillStyle='#ccdddd';ctx.fillRect(305,208+i*13,25,4);}};
   draw();setInterval(draw,40);const stream=c.captureStream(24);state.stream=stream;
   const track=stream.getVideoTracks()[0],get=track.getSettings.bind(track),stop=track.stop.bind(track);
   Object.defineProperty(track,'getCapabilities',{value:()=>({torch:supported})});
   Object.defineProperty(track,'getSettings',{value:()=>({...get(),torch:state.light})});
   Object.defineProperty(track,'applyConstraints',{value:async(c:any)=>{const value=c.advanced?.[0]?.torch;state.commands.push(value);if(!ignore&&track.readyState==='live')state.light=value;}});
   Object.defineProperty(track,'stop',{value:()=>{state.light=false;stop();}});
   return stream;
  }};Object.defineProperty(navigator,'mediaDevices',{configurable:true,get:()=>devices});
 },{supported,ignore});
}

test('all 25 catalogue families load and have selectable explanatory parts',async({page},info)=>{
 await session(page);await page.emulateMedia({reducedMotion:'reduce'});await page.goto('/vision-xray');
 await expect(page.getByTestId('vision-catalog-toggle')).toContainText('25');
 const list=await (await page.request.get('/api/vision-xray/catalog',{headers})).json();expect(list.models).toHaveLength(25);
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
 for(const entry of list.models){
  await page.getByTestId('vision-catalog-toggle').click();await page.getByTestId('vision-catalog-'+entry.canonical_key).click();
  const model=await (await page.request.get('/api/vision-xray/catalog/'+entry.model_id,{headers})).json();
  await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-part-count',String(model.manifest.parts.length));
  for(const part of [model.manifest.parts[0],model.manifest.parts.at(-1)]){
   await page.getByTestId('vision-part-'+part.key).click();await expect(page.getByTestId('vision-part-detail')).toContainText(part.name);
  }
  await expect(page.getByTestId('vision-close-model')).toBeVisible();
  if(['smartphone','soap_dispenser','stapler','earbud_charging_case'].includes(entry.canonical_key)){
   await page.getByTestId('vision-overview').click();await page.screenshot({path:'../.vision-evidence/catalog25-'+entry.canonical_key+'-'+info.project.name+'.png',fullPage:true});
   await expect(page.getByTestId('vision-how-it-works')).toBeVisible();
  }
 }
 expect(errors).toEqual([]);
});

test('catalogue search finds aliases and filters categories without changing the saved models',async({page},info)=>{
 await session(page);await page.goto('/vision-xray');await page.getByTestId('vision-catalog-toggle').click();
 const query=page.getByTestId('vision-catalog-search');await query.fill('telefono');
 await expect(page.getByTestId('vision-catalog-smartphone')).toBeVisible();
 await query.fill('thumb drive');await expect(page.getByTestId('vision-catalog-usb_flash_drive')).toBeVisible();
 await page.getByTestId('vision-catalog-category').selectOption('Casa');await expect(page.getByTestId('vision-catalog-category')).toHaveCSS('appearance','none');await expect(page.getByTestId('vision-catalog-count')).toContainText('0 di 25');
 await query.fill('');await expect(page.getByTestId('vision-catalog-clothespin')).toBeVisible();
 await expect(page.getByTestId('vision-catalog-smartphone')).toHaveCount(0);
 await page.screenshot({path:'../.vision-evidence/catalog25-search-'+info.project.name+'.png',fullPage:true});
});

test('supported flash toggles the existing video track, X keeps it and stop turns it off',async({page,browserName},info)=>{
 test.skip(browserName==='webkit','The headless camera fixture uses canvas captureStream, not physical WebKit hardware.');
 await session(page);await camera(page);await page.goto('/vision-xray');await page.getByTestId('vision-open-camera').click();
 const flash=page.getByTestId('vision-torch');await expect(flash).toBeEnabled();await flash.click();await expect(flash).toHaveAttribute('aria-pressed','true');
 expect(await page.evaluate(()=>(window as any).__cameraControls.light)).toBe(true);
 await flash.click();await expect(flash).toHaveAttribute('aria-pressed','false');
 await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-part-count','8');
 await flash.click();await expect(flash).toHaveAttribute('aria-pressed','true');
 await page.getByTestId('vision-camera-zoom-toggle').click();await page.getByTestId('vision-camera-zoom-2').click();
 await expect(page.getByTestId('vision-camera-video')).toHaveAttribute('data-camera-zoom','2.00');
 await page.getByTestId('vision-camera-zoom-toggle').click();
 await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-arrival','complete');
 await page.screenshot({path:'../.vision-evidence/camera-flash-zoom-'+info.project.name+'.png',fullPage:true});
 await page.getByTestId('vision-camera-zoom-toggle').click();
 await page.screenshot({path:'../.vision-evidence/camera-zoom-panel-'+info.project.name+'.png',fullPage:true});
 await page.getByTestId('vision-camera-zoom-toggle').click();
 await page.getByTestId('vision-close-model').click();expect(await page.evaluate(()=>(window as any).__cameraControls.opens)).toBe(1);
 await expect(flash).toHaveAttribute('aria-pressed','true');
 await page.getByTestId('vision-stop-camera').click();
 expect(await page.evaluate(()=>(window as any).__cameraControls.stream.getTracks().every((t:MediaStreamTrack)=>t.readyState==='ended'))).toBe(true);
 expect(await page.evaluate(()=>(window as any).__cameraControls.light)).toBe(false);
});

test('unsupported torch is explicit, and ignored torch command is never shown as on',async({page,browserName})=>{
 test.skip(browserName==='webkit','Synthetic stream unsupported here; capability fallbacks also have independent unit tests.');
 await session(page);await camera(page,false);await page.goto('/vision-xray');await page.getByTestId('vision-open-camera').click();
 await expect(page.getByTestId('vision-torch')).toBeDisabled();await expect(page.getByTestId('vision-torch')).toHaveAttribute('aria-label',/non disponibile/);
 await page.getByTestId('vision-stop-camera').click();
 // New page isolates the ignored-command fixture from the first session.
 const second=await page.context().newPage();await session(second);await camera(second,true,true);await second.goto('/vision-xray');await second.getByTestId('vision-open-camera').click();
 await second.getByTestId('vision-torch').click();await expect(second.getByTestId('vision-torch')).toHaveAttribute('aria-pressed','false');
 await expect(second.getByTestId('vision-torch')).toBeDisabled();await second.getByTestId('vision-stop-camera').click();await second.close();
});

test('camera zoom crops outgoing pixels and does not alter 3D zoom after acquisition',async({page,browserName})=>{
 test.skip(browserName==='webkit','Synthetic video only; geometry and WebKit catalogue are tested independently.');
 await session(page);await camera(page);const scans:any[]=[];
 await page.route('**/api/vision-xray/scan',async route=>{
  scans.push(route.request().postDataJSON());await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({status:'unknown',reason:'Fixture: attendi la prossima inquadratura'})});
 });
 await page.goto('/vision-xray');await page.getByTestId('vision-open-camera').click();await expect.poll(()=>scans.length).toBe(1);
 await page.getByTestId('vision-camera-zoom-toggle').click();await page.getByTestId('vision-camera-zoom-2').click();await expect.poll(()=>scans.length).toBe(2);
 const widths=await page.evaluate(async(images:string[])=>{
  const values=[];for(const encoded of images){
   const image=new Image();image.src='data:image/jpeg;base64,'+encoded;await image.decode();
   const c=document.createElement('canvas');c.width=image.width;c.height=image.height;const x=c.getContext('2d')!;x.drawImage(image,0,0);
   const data=x.getImageData(0,0,c.width,c.height).data;let left=c.width,right=0;
   for(let row=0;row<c.height;row++)for(let col=0;col<c.width;col++){const i=(row*c.width+col)*4;if(data[i]<70&&data[i+1]<85&&data[i+2]<90){left=Math.min(left,col);right=Math.max(right,col);}}
   values.push((right-left)/c.width);
  }return values;
 },scans.slice(0,2).map(s=>s.image_base64));
 expect(widths[1]/widths[0]).toBeGreaterThan(1.8);expect(widths[1]/widths[0]).toBeLessThan(2.2);
 await page.unroute('**/api/vision-xray/scan');await page.getByTestId('vision-camera-zoom-1').click();
 await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-part-count','8');
 await page.getByTestId('vision-zoom-in').click();await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-zoom','1.250');const modelZoom=await page.getByTestId('vision-scene').getAttribute('data-zoom');
 await page.getByTestId('vision-camera-zoom-3').click();await page.waitForTimeout(300);
 await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-zoom',modelZoom!);
 await page.getByTestId('vision-stop-camera').click();
});
