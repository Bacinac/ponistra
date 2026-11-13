import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: 'shots',
  testIgnore: 'shot.ts',
  testMatch: '*.ts',
  outputDir: '/tmp/results/shots',
  forbidOnly: true,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  workers: 2,
  retries: 1,
  reporter: 'line',
  use: { ...devices['Desktop Chrome'], baseURL: 'http://localhost:5173' },
});
