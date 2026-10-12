import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './e2e', testMatch: ['vision-live.spec.ts','vision-visual-v2.spec.ts','vision-guided-v3.spec.ts','vision-catalog-camera.spec.ts','vision-walkthrough25.spec.ts','vision-catalog75.spec.ts','vision-provider-recovery.spec.ts'], timeout: 90_000,
  expect: {timeout:30_000}, fullyParallel:false, workers:1,
  reporter:[['list'],['junit',{outputFile:'../.vision-evidence/browser-tests.xml'}]],
  use:{baseURL:'http://127.0.0.1:8765',trace:'retain-on-failure',screenshot:'only-on-failure'},
  projects:[
    {name:'chromium-desktop',use:{browserName:'chromium',viewport:{width:1440,height:960}}},
    {name:'chromium-mobile',use:{browserName:'chromium',viewport:{width:390,height:844},isMobile:true,hasTouch:true}},
    {name:'webkit-mobile',use:{browserName:'webkit',viewport:{width:390,height:844},isMobile:true,hasTouch:true}},
  ],
});
