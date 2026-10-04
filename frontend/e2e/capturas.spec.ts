import { expect, test } from '@playwright/test'

test.skip(!process.env.LECTOR_CAPTURAS, 'solo con LECTOR_CAPTURAS=1')

test.use({ viewport: { width: 1440, height: 900 }, colorScheme: 'light' })

test('capturas del modo demo', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Lecturas' }).click()
  await expect(page.locator('button[data-id]').first()).toBeVisible()
  await page.locator('button[data-id]').first().click()
  await page.screenshot({ path: '../docs/img/web-lecturas.png' })

  await page.getByRole('navigation').getByRole('button', { name: 'Procesar' }).click()
  await page.getByRole('radio', { name: /demo_entrada\.mp4/ }).click()
  await page.screenshot({ path: '../docs/img/web-procesar.png' })

  await page.getByRole('button', { name: 'Métricas' }).click()
  for (const label of [
    'Precisión de confirmadas auditadas',
    'Placas leídas completas',
    'Error por carácter',
    'Confirmación automática',
  ]) {
    await expect(page.getByText(label, { exact: true }).first()).toBeVisible()
  }
  await page.screenshot({ path: '../docs/img/web-metricas.png' })

  await page.getByRole('button', { name: 'Historial' }).click()
  await page.screenshot({ path: '../docs/img/web-historial.png' })
})
