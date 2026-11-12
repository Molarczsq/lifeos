import {defineConfig, devices} from '@playwright/test';
const port=process.env.E2E_PORT||'3000';
const baseURL='http://localhost:'+port;
export default defineConfig({
  testDir: './tests',
  timeout: 60000,
  use: {
    baseURL,
    ...devices['iPhone 13'],
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: {command:process.env.E2E_WEB_COMMAND||(process.env.CI?'node scripts/start-e2e.mjs':'pnpm dev --port '+port), url:baseURL, reuseExistingServer:!process.env.CI},
  reporter: 'list',
});
