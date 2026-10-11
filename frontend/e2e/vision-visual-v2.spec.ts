/** Built ORA UI and actual catalog via the existing isolated Mongo harness.
 * No production credentials. These are UI tests, not physical-device camera tests.
 */
import {test,expect,type Page} from '@playwright/test';
import {mkdirSync} from 'node:fs';
mkdirSync('../.vision-evidence',{recursive:true});
async function open(page:Page,family='remote_control'){
  await page.addInitScript(()=>localStorage.setItem('ora_auth_token',JSON.stringify('vision-test-alice')));
  await page.goto('/vision-xray');
  await expect(page.getByTestId('vision-live-explorer')).toHaveAttribute('data-version','visual-v2');
  await page.getByTestId('vision-catalog-toggle').click();
  await page.getByTestId('vision-catalog-'+family).click();
  await expect(page.getByTestId('vision-scene')).not.toHaveAttribute('data-part-count','0');
  await page.waitForTimeout(650);
}

test('camera-first overview and focused explanation fit the phone without hiding X',async({page},info)=>{
  const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));
  await open(page);
  await expect(page.getByTestId('vision-part-detail')).toHaveCount(0);
  const height=page.viewportSize()!.height;
  const stage=await page.getByTestId('vision-stage').boundingBox();expect(stage!.height).toBeGreaterThan(height*.55);
  const header=await page.locator('.vx-header').boundingBox();expect(header!.y).toBeGreaterThanOrEqual(0);
  const close=await page.getByTestId('vision-close-model').boundingBox();expect(close!.width).toBeGreaterThanOrEqual(44);expect(close!.y).toBeGreaterThan(header!.y+header!.height);
  await page.screenshot({path:'../.vision-evidence/vision-v2-overview-'+info.project.name+'.png',fullPage:true});
  await page.getByTestId('vision-part-pcb').click();
  await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-focused-part','pcb');
  await expect(page.getByTestId('vision-part-detail')).toContainText('Scheda elettronica');
  await page.waitForTimeout(700);
  await page.screenshot({path:'../.vision-evidence/vision-v2-focus-'+info.project.name+'.png',fullPage:true});
  await page.getByTestId('vision-more-detail').click();
  await expect(page.getByTestId('vision-part-detail')).toContainText('Come funziona.');
  await page.getByTestId('vision-collapse-detail').click();await expect(page.getByTestId('vision-detail-collapsed')).toBeVisible();
  await page.getByTestId('vision-expand-detail').click();await expect(page.getByTestId('vision-part-detail')).toBeVisible();
  await page.getByTestId('vision-overview').click();
  await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-focused-part','');
  await expect(page.getByTestId('vision-part-detail')).toHaveCount(0);
  await expect(page.getByTestId('vision-close-model')).toBeVisible();
  expect(errors).toEqual([]);
});

test('pinch zoom, buttons and keyboard rotate without selecting during a gesture',async({page})=>{
  await open(page);const scene=page.getByTestId('vision-scene');
  const initialYaw=await scene.getAttribute('data-yaw');
  await scene.dispatchEvent('pointerdown',{pointerId:31,pointerType:'touch',clientX:120,clientY:230});
  await scene.dispatchEvent('pointerdown',{pointerId:32,pointerType:'touch',clientX:220,clientY:230});
  await scene.dispatchEvent('pointermove',{pointerId:32,pointerType:'touch',clientX:260,clientY:230});
  await scene.dispatchEvent('pointerup',{pointerId:32,pointerType:'touch',clientX:260,clientY:230});
  await scene.dispatchEvent('pointerup',{pointerId:31,pointerType:'touch',clientX:120,clientY:230});
  await expect.poll(async()=>Number(await scene.getAttribute('data-zoom'))).toBeGreaterThan(1.2);
  await expect(scene).toHaveAttribute('data-focused-part','');await expect(scene).toHaveAttribute('data-yaw',initialYaw!);
  await scene.focus();await page.keyboard.press('0');await expect(scene).toHaveAttribute('data-zoom','1.000');
  await page.keyboard.press('ArrowRight');await expect(scene).not.toHaveAttribute('data-yaw',initialYaw!);
  await page.getByTestId('vision-zoom-in').click();await expect.poll(async()=>Number(await scene.getAttribute('data-zoom'))).toBeGreaterThan(1);
  await page.getByTestId('vision-zoom-out').click();await expect(scene).toHaveAttribute('data-zoom','1.000');
  await page.getByTestId('vision-explode-range').fill('45');await expect(page.getByTestId('vision-explode-range')).toHaveValue('45');
  await page.getByTestId('vision-toggle-explode').click();await expect(page.getByTestId('vision-explode-range')).toHaveValue('100');
});

test('all initial families render and remain selectable with reduced motion',async({page},info)=>{
  await page.emulateMedia({reducedMotion:'reduce'});await open(page);
  const cases=[['click_pen','spring','5'],['water_bottle','cap','3'],['computer_mouse','board','5'],['flashlight','battery','6']] as const;
  for(const [family,key,count] of cases){
    await page.getByTestId('vision-catalog-toggle').click();await page.getByTestId('vision-catalog-'+family).click();
    await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-part-count',count);
    await page.getByTestId('vision-part-'+key).click();
    await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-focused-part',key);
    await expect(page.getByTestId('vision-part-detail')).toBeVisible();
    await page.screenshot({path:'../.vision-evidence/vision-v2-'+family+'-'+info.project.name+'.png',fullPage:true});
  }
});

test('short and landscape viewports retain close, zoom and explanation controls',async({page})=>{
  await page.setViewportSize({width:390,height:640});await open(page);
  await page.getByTestId('vision-part-battery_a').click();
  for(const id of ['vision-close-model','vision-zoom-in','vision-overview']){
    const b=await page.getByTestId(id).boundingBox();expect(b!.y).toBeGreaterThanOrEqual(0);expect(b!.y+b!.height).toBeLessThanOrEqual(640);
  }
  await page.setViewportSize({width:844,height:390});await page.waitForTimeout(300);
  await expect(page.getByTestId('vision-close-model')).toBeVisible();
  await page.getByTestId('vision-overview').click();
  const root=await page.getByTestId('vision-live-explorer').boundingBox();expect(root!.height).toBeLessThanOrEqual(391);
  const canvas=await page.getByTestId('vision-scene').boundingBox();expect(canvas!.width).toBeGreaterThan(300);
});
