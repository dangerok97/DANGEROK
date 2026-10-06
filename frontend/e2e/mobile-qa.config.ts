import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';

const frontendRoot = path.resolve(__dirname, '..');
export default defineConfig({
  testDir: '.',
  testMatch: 'mobile-conversation-v93.spec.ts',
  outputDir: path.join(frontendRoot, 'test-results'),
  timeout: 90000,
  expect: { timeout: 15000 },
  workers: 1,
  retries: 0,
  reporter: [['list'], ['json', { outputFile: path.join(frontendRoot, 'mobile-qa/results.json') }]],
  use: { baseURL: 'http://127.0.0.1:8093', screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  projects: [
    { name: 'chromium-phone', use: { ...devices['iPhone 13'], browserName: 'chromium' } },
    { name: 'webkit-phone', use: { ...devices['iPhone 13'], browserName: 'webkit' } },
  ],
  webServer: {
    command: 'node e2e/mobile-qa-server.mjs',
    cwd: frontendRoot,
    url: 'http://127.0.0.1:8093',
    timeout: 15000,
    reuseExistingServer: false,
  },
});
