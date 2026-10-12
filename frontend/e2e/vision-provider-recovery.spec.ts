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
