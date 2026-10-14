import { defineConfig } from '@playwright/test';
import mobileQA from './mobile-qa.config';

export default defineConfig({
  ...mobileQA,
  testMatch: ['loyalty-wallet.spec.ts', 'vita-wallet-visibility.spec.ts', 'wallet-auto-import.spec.ts'],
});
