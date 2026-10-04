import { defineConfig } from '@playwright/test'

export const E2E_PORT = Number(process.env.LECTOR_E2E_PORT ?? '8799')
export const E2E_BASE = 'http://127.0.0.1:' + E2E_PORT

export default defineConfig({
  testDir: 'e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30_000,
  reporter: 'line',
  globalSetup: './e2e/global-setup.ts',
  use: { baseURL: E2E_BASE, storageState: 'e2e/.auth/state.json', trace: 'off' },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
})
