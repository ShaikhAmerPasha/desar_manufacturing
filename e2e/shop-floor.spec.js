import { test, expect } from '@playwright/test'
import { credentials } from './bench.js'

async function signIn(page, user, password) {
	const response = await page.request.post('/api/method/login', { data: { usr: user, pwd: password } })
	expect(response.ok()).toBeTruthy()
}

test('worker sees only the assigned inspection and submits it', async ({ page }) => {
	const { worker, password, assigned_roll, open_roll } = credentials()
	await signIn(page, worker, password)
	await page.goto('/shop-floor')
	await expect(page.getByText(assigned_roll)).toBeVisible()
	await expect(page.getByText(open_roll)).toHaveCount(0)
	await page.getByRole('button', { name: 'Open' }).click()
	await expect(page.getByText('COUNT THE PIECES OF EACH GRADE')).toBeVisible()
	const plus = page.getByRole('button', { name: '+' })
	await plus.nth(0).click()
	await plus.nth(0).click()
	await plus.nth(1).click()
	await expect(page.getByText('Total: 3')).toBeVisible()
	await page.getByRole('button', { name: 'Submit' }).click()
	await expect(page.getByText('No tasks assigned to you.')).toBeVisible()
})

test('worker cannot open a supervisor screen action', async ({ page }) => {
	const { worker, password } = credentials()
	await signIn(page, worker, password)
	const response = await page.request.post('/api/method/desar_manufacturing.api.shop_floor.assign_job_card', {
		data: { job_card: 'none', user: worker },
	})
	expect(response.status()).toBeGreaterThanOrEqual(400)
})

test('supervisor assigns an open roll to the worker', async ({ page }) => {
	const { supervisor, worker, password, open_roll, linked } = credentials()
	test.skip(!linked, 'Needs a submitted Work Order on the site to link rolls to.')
	await signIn(page, supervisor, password)
	await page.goto('/shop-floor/assign')
	const row = page.locator('div.rounded-xl', { hasText: open_roll })
	await row.getByRole('combobox').click()
	await page.getByRole('option').first().click()
	await row.getByRole('button', { name: 'Assign' }).click()
	await expect(page.getByText(open_roll)).toHaveCount(0)
	await signIn(page, worker, password)
	await page.goto('/shop-floor')
	await expect(page.getByText(open_roll)).toBeVisible()
})

test('Arabic switches to right to left', async ({ page }) => {
	const { worker, password } = credentials()
	await signIn(page, worker, password)
	await page.goto('/shop-floor')
	await page.getByRole('button', { name: 'العربية' }).click()
	await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
	await page.getByRole('button', { name: 'English' }).click()
	await expect(page.locator('html')).toHaveAttribute('dir', 'ltr')
})
