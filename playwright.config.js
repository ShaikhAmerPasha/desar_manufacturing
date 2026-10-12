import { defineConfig } from '@playwright/test'

export default defineConfig({
	testDir: './e2e',
	workers: 1,
	timeout: 60000,
	globalSetup: './e2e/global-setup.js',
	globalTeardown: './e2e/global-teardown.js',
	use: {
		baseURL: process.env.E2E_BASE_URL || 'http://localhost:8000',
		channel: process.env.E2E_CHANNEL || 'chrome',
		viewport: { width: 1180, height: 820 },
	},
})
