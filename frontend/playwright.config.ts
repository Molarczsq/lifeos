import {defineConfig,devices} from '@playwright/test';
export default defineConfig({testDir:'./tests',use:{baseURL:'http://localhost:3000',...devices['iPhone 13']},webServer:{command:'pnpm dev',url:'http://localhost:3000',reuseExistingServer:true},reporter:'list'});
