import { expect, test, type Page } from '@playwright/test'

test.skip(!process.env.LECTOR_CAPTURAS, 'solo con LECTOR_CAPTURAS=1')

test.use({ viewport: { width: 1440, height: 900 }, colorScheme: 'light' })

async function settle(page: Page) {
  await page.mouse.move(1430, 890)
  await expect(page.locator('.skeleton')).toHaveCount(0)
  await page.waitForLoadState('networkidle')
}

test('capturas del modo demo', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Lecturas' }).click()
  await expect(page.locator('button[data-id]').first()).toBeVisible()
  await page.locator('button[data-id]').first().click()
  await settle(page)
  await page.waitForFunction(() => Array.from(document.images).every((img) => img.complete))
  await page.screenshot({ path: '../docs/img/web-lecturas.png', animations: 'disabled' })

  await page.getByRole('navigation').getByRole('button', { name: 'Procesar' }).click()
  await page.getByRole('radio', { name: /demo_parqueadero\.webm/ }).click()
  await settle(page)
  await page.screenshot({ path: '../docs/img/web-procesar.png', animations: 'disabled' })

  await page.getByRole('button', { name: 'Métricas' }).click()
  for (const label of [
    'Precisión de confirmadas auditadas',
    'Placas leídas completas',
    'Error por carácter',
    'Confirmación automática',
  ]) {
    await expect(page.getByText(label, { exact: true }).first()).toBeVisible()
  }
  await settle(page)
  await page.screenshot({ path: '../docs/img/web-metricas.png', animations: 'disabled' })

  await page.getByRole('button', { name: 'Historial' }).click()
  await settle(page)
  await expect(page.locator('tbody tr').first()).toContainText('Video')
  await page.screenshot({ path: '../docs/img/web-historial.png', animations: 'disabled' })
})
