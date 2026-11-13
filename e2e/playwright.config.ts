import { defineConfig, devices } from '@playwright/test';

const started = process.env.PONISTRA_SESSION && JSON.parse(process.env.PONISTRA_SESSION);

export default defineConfig({
  testDir: 'tests',
  // Below what check.sh mounts at /tmp/results: Playwright clears its outputDir by removing it,
  // which a mount point in /tmp refuses.
  outputDir: '/tmp/results/last',
  forbidOnly: true,
  // The workers and the printer share the host with whatever else it carries; a full run also
  // counts every function they run and reads each chunk's source map.
  timeout: 60_000,
  expect: { timeout: 10_000 },
  // As many workers and tries as e2e_session started accounts for (tests/fixtures.ts).
  workers: started?.workers.length ?? 1,
  retries: started ? started.workers[0].length - 1 : 0,
  // A full run's report tells the gate which tests failed, for the next run to repeat them.
  reporter: process.env.PONISTRA_MAP
    ? [['line'], ['json', { outputFile: `${process.env.PONISTRA_MAP}/e2e-report.json` }]]
    : 'line',
  use: {
    ...devices['Desktop Chrome'],
    baseURL: 'http://localhost:5173',
    locale: 'hr-HR',
    viewport: { width: 1500, height: 900 },
  },
});
