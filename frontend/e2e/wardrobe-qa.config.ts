import { defineConfig, devices } from '@playwright/test';
import mobileQA from './mobile-qa.config';

export default defineConfig({
  ...mobileQA,
  testMatch: ['wardrobe-pilot.spec.ts'],
  projects: [
    { name: 'chromium-phone', use: { ...devices['iPhone 13'], browserName: 'chromium' } },
    { name: 'webkit-phone', use: { ...devices['iPhone 13'], browserName: 'webkit' } },
  ],
});
