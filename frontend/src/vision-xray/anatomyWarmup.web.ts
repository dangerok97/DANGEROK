/**
 * Best-effort prewarming of ONLY static public teaching assets. Never captures
 * camera pixels or user data, and never downloads all geometries up front.
 */
let requested:Promise<void>|null=null;
export function warmAnatomyReference():Promise<void>{
 if(typeof window==='undefined'||typeof fetch==='undefined')return Promise.resolve();
 const connection=(navigator as Navigator & {connection?:{saveData?:boolean;effectiveType?:string}}).connection;
 if(connection?.saveData||/^(slow-2g|2g)$/.test(connection?.effectiveType||''))return Promise.resolve();
 if(requested)return requested;
 requested=(async()=>{
  const staticAssets=['/bodyparts3d/ora-integrated.json','/bodyparts3d/models/atlas.json'];
  const index=await fetch('/bodyparts3d/index.html',{cache:'force-cache'}).then(r=>r.ok?r.text():'').catch(()=>'');
  const files=[...index.matchAll(/(?:src|href)="(\/bodyparts3d\/assets\/[^"]+)"/g)]
    .map(item=>item[1]).filter((item,index,list)=>list.indexOf(item)===index).slice(0,5);
  await Promise.allSettled([...staticAssets,...files].map(path=>
    fetch(path,{cache:'force-cache'}).then(response=>{if(!response.ok)throw Error('Reference not cached');})
  ));
 })().catch(()=>{requested=null;});
 return requested;
}
