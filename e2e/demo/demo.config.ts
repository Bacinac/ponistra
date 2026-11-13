import { defineConfig, devices } from '@playwright/test';

/** scripts/demo.sh: the recording over the check's stack, then the walk and the pictures over the
    built demo, each phase named by its file. */
export default defineConfig({
  testDir: '.',
  testMatch: '*.spec.ts',
  outputDir: '/tmp/results/demo',
  forbidOnly: true,
  timeout: 0,
  expect: { timeout: 10_000 },
  workers: 1,
  retries: 0,
  reporter: 'line',
  use: {
    ...devices['Desktop Chrome'],
    baseURL: 'http://localhost:5173',
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
  },
});
