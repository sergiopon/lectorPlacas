import { expect, test, type Page } from '@playwright/test'

test.describe.configure({ mode: 'serial' })

const consoleErrors: string[] = []

test.beforeEach(({ page }) => {
  consoleErrors.length = 0
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text())
  })
})

test.afterEach(() => {
  for (const text of consoleErrors) {
    expect(text).not.toContain('Content Security Policy')
    expect(text).not.toContain('Refused to')
  }
})

async function openReadings(page: Page) {
  await page.goto('/')
  await page.getByRole('button', { name: 'Lecturas' }).click()
}

test('revisar con el teclado', async ({ page }) => {
  await openReadings(page)
  await expect(page.getByRole('tab', { name: /Por revisar/ })).toContainText('15')
  await expect(page.getByRole('button', { name: /por revisar/ })).toContainText('15 por revisar')
  await page.locator('button[data-id]').first().click()
  await page.keyboard.press('c')
  await expect(page.getByRole('tab', { name: /Por revisar/ })).toContainText('14')
  await expect(page.getByRole('button', { name: /por revisar/ })).toContainText('14 por revisar')
})

test('corregir una placa', async ({ page }) => {
  await openReadings(page)
  await expect(page.getByRole('tab', { name: /Corregidas/ })).toContainText('5')
  await page.locator('button[data-id]').first().click()
  await page.keyboard.press('e')
  await page.keyboard.type('XYZ987')
  await page.keyboard.press('Enter')
  await expect(page.getByRole('tab', { name: /Corregidas/ })).toContainText('6')
})

test('ir al video', async ({ page }) => {
  await openReadings(page)
  await page.locator('button[data-id]').first().click()
  await page.keyboard.press('v')
  const video = page.locator('dialog video')
  await expect(video).toBeVisible()
  await expect
    .poll(async () => video.evaluate((el) => (el as HTMLVideoElement).readyState), { timeout: 10_000 })
    .toBeGreaterThanOrEqual(1)
  await expect(page.getByText('El video original no está disponible')).toBeHidden()
  await page.keyboard.press('Escape')
  await expect(page.locator('dialog')).toHaveCount(0)
  await page.keyboard.press('f')
  const img = page.locator('dialog img')
  await expect.poll(async () => img.evaluate((el) => (el as HTMLImageElement).naturalWidth)).toBeGreaterThan(0)
  await page.keyboard.press('Escape')
})

test('procesar un video de demo', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Procesar', exact: true }).first().click()
  await page.getByRole('radio', { name: /demo_parqueadero\.webm/ }).click()
  await page.getByRole('radio', { name: /Parqueadero o entrada/ }).click()
  await page.getByRole('button', { name: 'Procesar', exact: true }).last().click()
  await expect(page.getByRole('heading', { name: 'Resultado' })).toBeVisible({ timeout: 20_000 })
  await expect(page.getByRole('button', { name: /^Revisar \d+ placas$/ })).toBeVisible()
})

test('metricas y ajustes', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Métricas' }).click()
  for (const label of [
    'Precisión de confirmadas auditadas',
    'Placas leídas completas',
    'Error por carácter',
    'Confirmación automática',
  ]) {
    await expect(page.getByText(label, { exact: true }).first()).toBeVisible()
  }
  await page.getByRole('button', { name: 'Ajustes' }).click()
  await page.getByRole('button', { name: 'Exportar CSV' }).click()
  await expect(page.getByText(/^Exportado a data\/exports\//)).toBeVisible()
})
