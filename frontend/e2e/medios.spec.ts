import { expect, test } from '@playwright/test'

test.skip(!process.env.LECTOR_MEDIOS, 'solo con LECTOR_MEDIOS=1')

test.use({
  viewport: { width: 1280, height: 720 },
  colorScheme: 'light',
  video: { mode: 'on', size: { width: 1280, height: 720 } },
})

test('recorrido para el README', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Procesar', exact: true }).first().click()
  await page.getByRole('radio', { name: /demo_parqueadero\.webm/ }).click()
  await page.getByRole('button', { name: 'Procesar', exact: true }).last().click()
  await expect(page.getByRole('heading', { name: 'Resultado' })).toBeVisible({ timeout: 20_000 })
  await page.waitForTimeout(1200)

  await page.getByRole('navigation').getByRole('button', { name: 'Lecturas' }).click()
  await expect(page.locator('button[data-id]').first()).toBeVisible()
  await page.waitForTimeout(1000)
  await page.locator('button[data-id]').first().click()
  await page.waitForTimeout(800)
  await page.keyboard.press('c')
  await page.waitForTimeout(1000)

  await page.keyboard.press('v')
  const video = page.locator('dialog video')
  await expect
    .poll(async () => video.evaluate((el) => (el as HTMLVideoElement).readyState))
    .toBeGreaterThanOrEqual(2)
  await page.waitForTimeout(3000)
  await page.screenshot({ path: '../docs/img/web-video.png', animations: 'disabled' })
  await page.keyboard.press('Escape')
  await page.waitForTimeout(500)

  await page.keyboard.press('f')
  await expect(page.locator('dialog img')).toBeVisible()
  await page.waitForTimeout(2000)
  await page.keyboard.press('Escape')
  await page.waitForTimeout(800)

  await page.close()
  await page.video()!.saveAs('../docs/img/demo.webm')
})
