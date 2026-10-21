import { defineConfig } from '@playwright/test';
import mobileQA from './e2e/mobile-qa.config';

export default defineConfig({
  ...mobileQA,
  testDir: './e2e',
  testMatch: ['house-scans.spec.ts'],
  outputDir: './test-results/house-scans',
  reporter: [['list'], ['json', { outputFile: './mobile-qa/house-scans-results.json' }]],
  projects: mobileQA.projects?.map(project => project.name === 'chromium-phone' && process.env.ORA_QA_CHROMIUM_EXECUTABLE ? {
    ...project,
    use: { ...project.use, launchOptions: {
      executablePath: process.env.ORA_QA_CHROMIUM_EXECUTABLE,
      args: ['--no-sandbox', '--disable-dev-shm-usage'],
    } },
  } : project),
});
