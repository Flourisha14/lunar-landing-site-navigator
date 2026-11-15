import { defineConfig, devices } from '@playwright/test';

const port = 5173;

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 45_000,
  expect: { timeout: 12_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'list',
  use: {
    ...devices['Desktop Chrome'],
    baseURL: `http://localhost:${port}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: {
      args: [
        '--enable-webgl',
        '--enable-unsafe-swiftshader',
        '--use-angle=swiftshader',
        '--disable-gpu-sandbox',
      ],
    },
  },
  webServer: {
    command: 'npm run dev -- --host localhost',
    url: `http://localhost:${port}`,

    // Ensure browser regressions use a controlled test environment.
    reuseExistingServer: false,
    timeout: 120_000,

    // Vite must not load authenticated Cesium Moon during
    // reference-sphere regression tests.
    env: {
      VITE_CESIUM_ION_TOKEN: '',
    },
  },
});
