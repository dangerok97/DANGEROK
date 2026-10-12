/** Compiled ORA + actual disposable Mongo. No provider calls or physical-camera claim. */
import {test,expect} from '@playwright/test';
import {readFileSync,mkdirSync} from 'node:fs';
const baseline=new Set(Object.keys(JSON.parse(readFileSync('../backend/vision_tests/fixtures/legacy25_sha256.json','utf8'))));
const headers={Authorization:'Bearer vision-test-alice'};
mkdirSync('../.vision-evidence',{recursive:true});

for(const [start,end] of [[0,13],[13,26],[26,39],[39,50]])test(`new catalog batch ${start+1}–${end}: render, focus and preserve old tours`,async({page},info)=>{
 await page.addInitScript(()=>localStorage.setItem('ora_auth_token',JSON.stringify('vision-test-alice')));
 await page.emulateMedia({reducedMotion:'reduce'});await page.goto('/vision-xray');
 await expect(page.getByTestId('vision-catalog-toggle')).toContainText('160');
 const list=await(await page.request.get('/api/vision-xray/catalog',{headers})).json();
 expect(list.models).toHaveLength(160);
 const added=list.models.filter((m:any)=>!baseline.has(m.canonical_key)).slice(0,50);expect(added).toHaveLength(50);
 const errors:string[]=[],scans:string[]=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('request',r=>{if(r.url().endsWith('/api/vision-xray/scan'))scans.push(r.url());});
 for(const entry of added.slice(start,end)){
  await page.getByTestId('vision-catalog-toggle').click();
  await page.getByTestId('vision-catalog-search').fill(entry.title);
  await page.getByTestId('vision-catalog-'+entry.canonical_key).click();
  const model=await(await page.request.get('/api/vision-xray/catalog/'+entry.model_id,{headers})).json();
  const scene=page.getByTestId('vision-scene');
  await expect(scene).toHaveAttribute('data-part-count',String(model.manifest.parts.length));
  await expect(page.getByTestId('vision-how-it-works')).toHaveCount(0);
  for(const part of [model.manifest.parts[0],model.manifest.parts.at(-1)]){
   await page.getByTestId('vision-part-'+part.key).click();
   await expect(scene).toHaveAttribute('data-focused-part',part.key);
   await expect(page.getByTestId('vision-part-detail')).toContainText(part.name);
  }
  await page.getByTestId('vision-overview').click();
  await expect(page.getByTestId('vision-close-model')).toBeVisible();
  if(['moka_pot','manual_coffee_grinder','zipper','spinning_reel','binoculars','overear_headphones','umbrella','diatonic_harmonica'].includes(entry.canonical_key)){
   await page.screenshot({path:`../.vision-evidence/catalog75-${entry.canonical_key}-${info.project.name}.png`,fullPage:true});
  }
 }
 expect(errors).toEqual([]);expect(scans).toEqual([]);
});

test('new Italian aliases and categories are searchable without duplicate records',async({page},info)=>{
 await page.addInitScript(()=>localStorage.setItem('ora_auth_token',JSON.stringify('vision-test-alice')));
 await page.goto('/vision-xray');await page.getByTestId('vision-catalog-toggle').click();
 const search=page.getByTestId('vision-catalog-search'),category=page.getByTestId('vision-catalog-category');
 for(const [query,key] of [['macinacaffè manuale','manual_coffee_grinder'],['cassa bluetooth','portable_speaker'],['mulinello','spinning_reel'],['cerniera lampo','zipper']]){
  await search.fill(query);await expect(page.getByTestId('vision-catalog-'+key)).toBeVisible();
 }
 await search.fill('');await category.selectOption('Cucina');
 await expect(page.getByTestId('vision-catalog-moka_pot')).toBeVisible();
 await expect(page.getByTestId('vision-catalog-smartphone')).toHaveCount(0);
 await page.screenshot({path:`../.vision-evidence/catalog75-search-${info.project.name}.png`,fullPage:true});
 await category.selectOption('Tempo libero');await expect(page.getByTestId('vision-catalog-spinning_reel')).toBeVisible();
 await search.fill('nessunoggettozz');await expect(page.getByTestId('vision-catalog-count')).toContainText('0 di 160');
 const listed=await(await page.request.get('/api/vision-xray/catalog',{headers})).json();expect(listed.models).toHaveLength(160);
});
