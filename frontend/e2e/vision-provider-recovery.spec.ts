import {test,expect} from '@playwright/test';
// Synthetic PNG: no user's photograph is committed or sent by this UI suite.
const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=','base64');
test.beforeEach(async({page})=>{await page.addInitScript(()=>localStorage.setItem('ora_auth_token',JSON.stringify('vision-test-alice')));});

test('provider timeout is not displayed as an unrecognized object',async({page})=>{
 await page.route('**/api/vision-xray/scan',route=>route.fulfill({status:504,contentType:'application/json',body:JSON.stringify({detail:{code:'provider_timeout',message:'Il servizio visivo non ha risposto in tempo. Riprova fra poco.'}})}));
 await page.goto('/vision-xray');await page.locator('input[type=file]').setInputFiles({name:'fixture.png',mimeType:'image/png',buffer:png});
 await expect(page.getByTestId('vision-error')).toContainText('non ha risposto in tempo');
 await expect(page.getByTestId('vision-recovery')).toHaveCount(0);
 await expect(page.getByTestId('vision-status')).not.toContainText('Non distinguo');
});

test('uncertain image offers a hint and sends it for visual verification',async({page},info)=>{
 const payloads:any[]=[];
 await page.route('**/api/vision-xray/scan',async route=>{
  payloads.push(route.request().postDataJSON());
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({status:'unknown',code:'recognition_uncertain',can_describe:true,reason:'Non riesco ancora a identificarlo. Puoi indicarmi che oggetto è: lo verifico nella foto.'})});
 });
 await page.goto('/vision-xray');await page.locator('input[type=file]').setInputFiles({name:'fixture.png',mimeType:'image/png',buffer:png});
 await expect(page.getByTestId('vision-recovery')).toBeVisible();
 await expect(page.getByTestId('vision-identify-hint')).toBeDisabled();
 await page.getByTestId('vision-object-hint').fill('un telecomando');
 await page.getByTestId('vision-identify-hint').click();
 await expect.poll(()=>payloads.length).toBe(2);
 expect(payloads[0].object_hint).toBe('');expect(payloads[1].object_hint).toBe('un telecomando');
 expect(payloads[1].image_base64).toBeTruthy();expect(payloads[1].allow_generation).toBe(true);
 await expect(page.getByTestId('vision-recovery')).toBeVisible();
 await page.screenshot({path:'../.vision-evidence/vision-hint-'+info.project.name+'.png',fullPage:true});
 await page.getByTestId('vision-catalog-toggle').click();await page.getByTestId('vision-catalog-remote_control').click();
 await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-part-count','8');
 await expect(page.getByTestId('vision-recovery')).toHaveCount(0);
});


test('automatic retries pause while the user supplies an object hint',async({page,browserName})=>{
 test.skip(browserName==='webkit','Synthetic canvas video is not a physical WebKit camera test.');
 let scans=0;
 await page.addInitScript(()=>{
  const devices={getUserMedia:async()=>{
   const canvas=document.createElement('canvas');canvas.width=320;canvas.height=480;const ctx=canvas.getContext('2d')!;let n=0;
   const draw=()=>{ctx.fillStyle=++n%2?'#aabbcc':'#334455';ctx.fillRect(0,0,320,480);ctx.fillStyle='#222';ctx.fillRect(90,90,140,250);};
   draw();setInterval(draw,120);return canvas.captureStream(24);
  }};Object.defineProperty(navigator,'mediaDevices',{configurable:true,get:()=>devices});
 });
 await page.route('**/api/vision-xray/scan',route=>{scans++;return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({status:'unknown',code:'recognition_uncertain',can_describe:true,reason:'Puoi indicarmi che oggetto è.'})});});
 await page.goto('/vision-xray');await page.getByTestId('vision-open-camera').click();
 await expect(page.getByTestId('vision-recovery')).toBeVisible();
 await page.getByTestId('vision-object-hint').fill('un telecomando');
 await page.waitForTimeout(7000);
 expect(scans).toBe(1);await expect(page.getByTestId('vision-object-hint')).toHaveValue('un telecomando');
 await page.getByTestId('vision-identify-hint').click();await expect.poll(()=>scans).toBe(2);
 await page.getByTestId('vision-stop-camera').click();await expect(page.getByTestId('vision-recovery')).toHaveCount(0);
});
