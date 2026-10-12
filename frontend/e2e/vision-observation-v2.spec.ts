import {test,expect,type Page} from '@playwright/test';
import {mkdirSync} from 'node:fs';
mkdirSync('../.vision-evidence',{recursive:true});
async function photo(page:Page){
 const bytes=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=160;c.height=160;const x=c.getContext('2d')!;x.fillStyle='#b5b0a4';x.fillRect(0,0,160,160);x.fillStyle='#555';x.fillRect(40,30,80,105);return Array.from(atob(c.toDataURL('image/jpeg').split(',')[1]),ch=>ch.charCodeAt(0));});
 await page.locator('input[type=file]').setInputFiles({name:'synthetic-object.jpg',mimeType:'image/jpeg',buffer:Buffer.from(bytes)});
}
async function start(page:Page){await page.addInitScript(()=>localStorage.setItem('ora_auth_token',JSON.stringify('vision-test-alice')));await page.goto('/vision-xray');await expect(page.getByTestId('vision-live-explorer')).toBeVisible();}

test('real uncertainty offers a bounded hint and sends it with a fresh image',async({page},info)=>{
 const requests:any[]=[];
 await page.route('**/api/vision-xray/scan',async route=>{
  requests.push(route.request().postDataJSON());
  await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({status:'unknown',error_code:'object_uncertain',can_hint:true,reason:'Non riesco ancora a identificare questo oggetto. Puoi indicarne il nome oppure mostrare un altro lato.'})});
 });
 await start(page);await photo(page);
 await expect(page.getByTestId('vision-recognition-help')).toBeVisible();
 await expect(page.getByTestId('vision-hint-submit')).toBeDisabled();
 await page.getByTestId('vision-object-hint').fill('pattumiera con coperchio');
 await expect(page.getByTestId('vision-hint-submit')).toBeEnabled();
 await page.screenshot({path:'../.vision-evidence/vision-identity-help-'+info.project.name+'.png',fullPage:true});
 await page.getByTestId('vision-hint-submit').click();
 await expect.poll(()=>requests.length).toBe(2);
 expect(requests[0].object_hint).toBe('');expect(requests[1].object_hint).toBe('pattumiera con coperchio');
 expect(requests[1].image_base64.length).toBeGreaterThan(100);
 await expect(page.getByTestId('vision-scene')).toHaveAttribute('data-part-count','0');
});

test('AI service failure is never shown as a bad photograph',async({page},info)=>{
 await page.route('**/api/vision-xray/scan',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:{code:'provider_quota',message:'Il servizio AI ha raggiunto un limite di utilizzo. Non è un problema dell’inquadratura.'}})}));
 await start(page);await photo(page);
 await expect(page.getByTestId('vision-error')).toContainText('limite di utilizzo');
 await expect(page.getByTestId('vision-error')).toContainText('Non è un problema dell’inquadratura');
 await expect(page.getByTestId('vision-recognition-help')).toHaveCount(0);
 await expect(page.getByTestId('vision-status')).not.toContainText('Non distinguo');
 await page.screenshot({path:'../.vision-evidence/vision-provider-error-'+info.project.name+'.png',fullPage:true});
});
