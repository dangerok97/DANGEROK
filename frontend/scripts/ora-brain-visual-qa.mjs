/**
 * Visual acceptance for the ORA 3D particle brain, not the anatomical atlas.
 * Runs the actual built /bodyparts3d/?ora=brain bundle on mobile Chromium/WebKit.
 * It also verifies a synthetic knowledge-star selection crosses the existing
 * same-origin bridge. No user data, login, or network API calls.
 */
import {chromium,webkit} from '@playwright/test';
import {createServer} from 'node:http';
import {readFile,stat,mkdir} from 'node:fs/promises';
import {join,resolve,sep,extname} from 'node:path';
import process from 'node:process';

const root=resolve(process.argv[2]||'');
const output=resolve(process.argv[3]||'ora-brain-visual-qa');
await mkdir(output,{recursive:true});
const mime={'.js':'text/javascript','.css':'text/css','.html':'text/html',
  '.json':'application/json','.png':'image/png','.svg':'image/svg+xml',
  '.woff2':'font/woff2','.ico':'image/x-icon'};
const fixture=`<!doctype html><html lang="it"><head><meta name="viewport" content="width=device-width, initial-scale=1">
<style>*{box-sizing:border-box}html,body{margin:0;background:#02060c}iframe{display:block;border:0;width:390px;height:680px;max-width:100vw}</style></head>
<body><iframe id="brain" title="Cervello ORA" src="/bodyparts3d/?ora=brain"></iframe>
<script>
window.messages=[];
window.addEventListener('message',event=>{
 if(event.origin===location.origin && event.source===document.getElementById('brain').contentWindow)
  window.messages.push(event.data);
});
</script></body></html>`;
const server=createServer(async(req,res)=>{
 try{
  let pathname=new URL(req.url||'/', 'http://localhost').pathname;
  if(pathname==='/__brain_test__'){res.setHeader('Content-Type','text/html');res.end(fixture);return;}
  if(!pathname.startsWith('/bodyparts3d/')){res.writeHead(404).end();return;}
  let path=pathname.slice('/bodyparts3d/'.length);
  if(!path || path.endsWith('/'))path+='index.html';
  const absolute=resolve(root,path);
  if(absolute!==root && !absolute.startsWith(root+sep)){res.writeHead(403).end();return;}
  let file=absolute;
  try{if(!(await stat(file)).isFile())throw new Error('not a file');}
  catch{
   if(extname(path)){res.writeHead(404).end();return;}
   file=join(root,'index.html');
  }
  res.setHeader('Content-Type',mime[extname(file)]||'application/octet-stream');
  res.setHeader('Cache-Control','no-store');
  res.end(await readFile(file));
 }catch(error){res.writeHead(500).end(String(error));}
});
await new Promise((ok,fail)=>{server.once('error',fail);server.listen(0,'127.0.0.1',ok);});
const address=server.address();
const base='http://127.0.0.1:'+address.port;
let failed=false;
try{
 for(const [name,engine] of [['chromium',chromium],['webkit',webkit]]){
  let browser;
  try{
   browser=await engine.launch({headless:true,...(name==='chromium'?{
     args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader']
   }:{})});
   const page=await browser.newPage({viewport:{width:390,height:844},deviceScaleFactor:2,
     isMobile:true,hasTouch:true,reducedMotion:'reduce'});
   const problems=[];
   page.on('pageerror',error=>problems.push('pageerror: '+error.message));
   page.on('console',msg=>{
    if(msg.type()==='error' && /WebGL|shader|THREE|Failed|SyntaxError/i.test(msg.text()))
      problems.push('console: '+msg.text());
   });
   await page.goto(base+'/__brain_test__',{waitUntil:'load',timeout:30000});
   await page.waitForFunction(()=>window.messages.some(m=>m?.type==='ora:brain-ready'),null,{timeout:35000});
   const marker=page.frameLocator('#brain').locator('[data-visual-profile="particle-hologram-v184"]');
   await marker.waitFor({state:'visible'});
   const canvas=page.frameLocator('#brain').locator('.ora-brain-host canvas');
   await canvas.waitFor({state:'visible'});
   const context=await canvas.evaluate(el=>{
     const gl=el.getContext('webgl2')||el.getContext('webgl');
     return Boolean(gl&&!gl.isContextLost());
   });
   if(!context)throw new Error(name+': WebGL context unavailable or lost');
   const ready=await page.evaluate(()=>window.messages.find(m=>m?.type==='ora:brain-ready'));
   if(!ready||ready.visualProfile!=='particle-hologram-v184'||ready.particleCount<8000)
    throw new Error(name+': missing/undersized actual 3D particle field '+JSON.stringify(ready));
   await page.evaluate(()=>{
     document.getElementById('brain').contentWindow.postMessage({
       type:'ora:brain-state',version:1,options:{mode:'think',paused:false,reduced:false,
       stars:[{id:'synthetic_test_memory',area:'memory',kind:'node',complete:true},
              {id:'synthetic_test_temporary',area:'calendar',kind:'node',temporary:true}]}
     },location.origin);
   });
   await page.frameLocator('#brain').getByRole('button',{name:/Apri memoria/i}).waitFor();
   await page.waitForTimeout(700);
   await page.locator('#brain').screenshot({path:join(output,'ora-brain-'+name+'-390x680.png')});
   await page.frameLocator('#brain').getByRole('button',{name:/Apri memoria/i}).click();
   await page.waitForFunction(()=>window.messages.some(m=>m?.type==='ora:brain-select'&&m.node?.area==='memory'),null,{timeout:12000});
   if(problems.length)throw new Error(name+': '+problems.join(' | '));
   const result={browser:name,particleCount:ready.particleCount,context:true,
      labels:await page.frameLocator('#brain').locator('.ora-brain-label').count(),
      selected:true,screenshot:'ora-brain-'+name+'-390x680.png'};
   process.stdout.write(JSON.stringify(result)+'\n');
  }catch(error){
    failed=true;process.stderr.write('ORA brain '+name+' visual QA failed: '+String(error)+'\n');
  }finally{await browser?.close();}
 }
}finally{
 await new Promise(resolve=>server.close(resolve));
}
if(failed)process.exitCode=1;
