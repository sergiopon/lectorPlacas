# 077 - Frontend: escalas de los gráficos de métricas y capturas estables

## Objetivo
Corregir dos fallos vistos en las capturas de la spec 072 (2026-10-04):
1. En "Métricas", el gráfico de líneas usa escalas fijas (precisión 80–100 %, error por carácter 0–8 %). Con la demo
   (error por carácter 16,7 %) la línea del error se dibuja fuera de su panel, encima del de precisión. Las escalas pasan
   a ajustarse a los datos.
2. Las capturas se tomaban antes de que la página terminara de cargar (esqueletos en "Historial", transiciones de la
   navegación a medias). El script espera a que no haya esqueletos ni peticiones pendientes y desactiva animaciones.

## Depende de
070, 071, 072.

## Archivos rectores aplicables
- docs/08 §4.6 (pantalla Métricas); reglas-seguridad.md SEG-10 (capturas solo del modo demo).

## Archivos a crear/modificar
- `frontend/src/lib/chart.ts` (nuevo)
- `frontend/src/screens/Metricas.tsx` (solo la función `Lines`)
- `frontend/tests/unit/chart.test.ts` (nuevo)
- `frontend/e2e/capturas.spec.ts`
- `docs/img/web-lecturas.png`, `docs/img/web-procesar.png`, `docs/img/web-metricas.png`, `docs/img/web-historial.png`
  (regeneradas con el comando del Definition of Done)

## Dependencias externas
Ninguna nueva. Playwright 1.63.0: `page.screenshot({ path, animations: "disabled" })` y
`page.waitForLoadState("networkidle")`.

## Comportamiento esperado

### 1. `src/lib/chart.ts`
- `export function upperBound(values: (number | null)[], minHi: number, step: number): number`: con `m` = el máximo de
  los valores no nulos, devuelve `Math.max(minHi, Math.ceil(m / step) * step)`; sin valores no nulos, `minHi`.
- `export function lowerBound(values: (number | null)[], maxLo: number, step: number): number`: con `m` = el mínimo de
  los valores no nulos, devuelve `Math.min(maxLo, Math.floor(m / step) * step)`; sin valores no nulos, `maxLo`.
- Ambas: si el resultado tiene error de coma flotante, se redondea con `Math.round(r * 1000) / 1000`.

### 2. `Lines` en `Metricas.tsx`
- Panel de precisión: `lo = lowerBound(precisiones, 0.8, 0.1)`, `hi = 1`.
- Panel de error por carácter: `lo = 0`, `hi = upperBound(errores, 0.08, 0.05)`.
- El resto del componente no cambia (rótulos de eje con `Math.round(t * 100)` y `%`).

### 3. `e2e/capturas.spec.ts`
Antes de **cada** `page.screenshot`, en este orden:
1. `await page.mouse.move(1430, 890)` (fuera de botones, para que no quede ningún estado `hover`).
2. `await expect(page.locator(".skeleton")).toHaveCount(0)`.
3. `await page.waitForLoadState("networkidle")`.
4. En "Lecturas", además, todas las imágenes visibles terminaron de cargar:
   `await page.waitForFunction(() => Array.from(document.images).every((img) => img.complete))`.
5. En "Historial", además, `await expect(page.locator("tbody tr").first()).toContainText("Video")`.

Cada captura usa `page.screenshot({ path, animations: "disabled" })`. El resto del script (orden, rutas, viewport, tema
claro, `test.skip` sin `LECTOR_CAPTURAS`) no cambia.

## Casos borde y manejo de errores
- Sin datos de métricas, `perVideo` vacío: no se dibujan los gráficos (spec 070); las funciones no se llaman.

## Tests de aceptación (en prosa)
`tests/unit/chart.test.ts`:
- `upperBound ajusta al dato`: `upperBound([0.167, null], 0.08, 0.05)` ≈ `0.2`; `upperBound([0.03], 0.08, 0.05)` es
  `0.08`; `upperBound([null], 0.08, 0.05)` es `0.08`.
- `lowerBound ajusta al dato`: `lowerBound([0.62, 0.9], 0.8, 0.1)` ≈ `0.6`; `lowerBound([0.95], 0.8, 0.1)` es `0.8`;
  `lowerBound([], 0.8, 0.1)` es `0.8`.
(`≈` = `toBeCloseTo` con 6 decimales.)

## Fuera de alcance
- Cambiar el diseño de los gráficos o de otras pantallas.

## Definition of Done
- [ ] En `frontend/`: `npm ci`, `npm run typecheck`, `npm test`, `npm run build` y `npm run e2e` en verde.
- [ ] En `frontend/`: `LECTOR_CAPTURAS=1 npx playwright test e2e/capturas.spec.ts` regenera los cuatro PNG
      (`ls -l ../docs/img`).
- [ ] `uv run pytest -q` en verde.
