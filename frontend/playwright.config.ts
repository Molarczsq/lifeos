import {defineConfig, devices} from '@playwright/test';
export default defineConfig({
  testDir: './tests',
  timeout: 60000,
  use: {
    baseURL: 'http://localhost:3000',
    ...devices['iPhone 13'],
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: {command:'pnpm dev', url:'http://localhost:3000', reuseExistingServer:!process.env.CI},
  reporter: 'list',
});
