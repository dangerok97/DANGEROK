import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  testMatch: 'mobile-conversation-v93.spec.ts',
  timeout: 90000,
  expect: { timeout: 15000 },
  workers: 1,
  retries: 0,
  reporter: [['list'], ['json', { outputFile: 'mobile-qa/results.json' }]],
  use: { baseURL: 'http://127.0.0.1:8093', screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  projects: [
    { name: 'chromium-phone', use: { ...devices['iPhone 13'], browserName: 'chromium' } },
    { name: 'webkit-phone', use: { ...devices['iPhone 13'], browserName: 'webkit' } },
  ],
  webServer: { command: 'node e2e/mobile-qa-server.mjs', url: 'http://127.0.0.1:8093', timeout: 15000, reuseExistingServer: false },
});
