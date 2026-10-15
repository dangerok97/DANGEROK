/** Isolated, unauthenticated visual smoke for the compiled ORA brain viewer.
 * Test data contains only synthetic geometry IDs. Never use a real account.
 */
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdtempSync,mkdirSync,symlinkSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {chromium} from '@playwright/test';

const dist=resolve(process.argv[2]||'');
if(!dist||dist===process.cwd())throw Error('Usage: node scripts/ora-brain-browser-qa.mjs <BodyParts3D dist>');
const root=mkdtempSync(join(tmpdir(),'ora-brain-visual-'));
const out=resolve(process.argv[3]||'../.ora-brain-qa');
mkdirSync(out,{recursive:true});
symlinkSync(dist,join(root,'bodyparts3d'),'dir');
const port=8766,url='http://127.0.0.1:'+port+'/bodyparts3d/?ora=brain';
const server=spawn('python3',['-m','http.server',String(port),'--bind','127.0.0.1','--directory',root],{stdio:'ignore'});
let browser;
try{
 let ready=false;
 for(let i=0;i<50;i++){
  try{const response=await fetch(url);if(response.ok){ready=true;break;}}catch{}
  await new Promise(r=>setTimeout(r,200));
 }
 assert(ready,'BodyParts3D preview HTTP server failed to start');
 browser=await chromium.launch({headless:true,args:['--use-gl=angle','--use-angle=swiftshader-webgl','--enable-webgl']});
 const page=await browser.newPage({viewport:{width:390,height:844},deviceScaleFactor:1.5});
 const pageErrors=[];
 page.on('pageerror',error=>pageErrors.push(error.message));
 await page.goto(url,{waitUntil:'domcontentloaded',timeout:30000});
 const scene=page.locator('[data-testid="ora-brain-webgl"]');
 await scene.waitFor({timeout:30000});
 await page.waitForFunction(()=>document.querySelector('[data-testid="ora-brain-webgl"]')?.getAttribute('data-status')==='ready',{timeout:25000});
 assert.equal(await scene.getAttribute('data-visual-profile'),'particle-hologram-v184');
 await page.evaluate(()=>{
  window.postMessage({type:'ora:brain-state',version:1,options:{
   mode:'think',active:true,resetKey:1,zoomOverride:1,
   stars:[
    {id:'visual_mock_a',area:'memory',kind:'node'},
    {id:'visual_mock_b',area:'calendar',kind:'node'},
    {id:'visual_mock_c',area:'people',kind:'node'},
    {id:'visual_mock_d',area:'places',kind:'node'},
    {id:'visual_mock_temp',area:'home',kind:'node',temporary:true},
    {id:'visual_mock_tentative',area:'documents',kind:'node',tentative:true}
   ]}},location.origin);
 });
 await page.waitForTimeout(1350);
 assert.equal(await page.locator('.ora-brain-label').count(),4,'four exterior callouts expected');
 const canvas=page.locator('canvas');
 assert(await canvas.count()>=1,'WebGL canvas absent');
 const dims=await canvas.evaluate(el=>({width:el.width,height:el.height}));
 assert(dims.width>=390&&dims.height>=844,'WebGL canvas dimensions invalid');
 assert.equal(await scene.getAttribute('data-status'),'ready','Renderer lost WebGL context');
 assert.deepEqual(pageErrors,[],'Client-side browser exceptions');
 const screenshot=join(out,'ora-brain-v184-chromium-390x844.png');
 await page.screenshot({path:screenshot,animations:'disabled'});
 console.log(JSON.stringify({profile:'particle-hologram-v184',status:'PASS',dimensions:dims,
  labels:4,screenshot,errors:pageErrors.length}));
}finally{
 if(browser)await browser.close();
 server.kill('SIGTERM');
 rmSync(root,{recursive:true,force:true});
}
