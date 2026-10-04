# 071 - Frontend: pruebas de componentes (Vitest) y de punta a punta (Playwright contra el modo demo)

## Objetivo
Cubrir con pruebas automáticas el frontend integrado en la spec 070:
1. **Unitarias y de componentes** (Vitest + Testing Library, sin servidor): el cliente HTTP, el mapeo de la API y los
   componentes que cambiaron en la 070.
2. **De punta a punta** (Playwright + Chromium) contra `lector-web --demo` real: revisar placas con el teclado,
   procesar un video de demo, abrir "Ir al video", métricas y ajustes, comprobando además que el navegador no registra
   violaciones de la CSP de SEG-28.

No cambia ningún archivo de `frontend/src/` ni de `src/`.

## Depende de
064, 069, 070, 076.

## Archivos rectores aplicables
- reglas-seguridad.md SEG-10 (solo datos sintéticos: el modo demo), SEG-28 (CSP).
- docs/06-plan-pruebas.md; docs/08 §4.7.

## Archivos a crear/modificar
- `frontend/package.json` (dependencias y scripts), `frontend/package-lock.json` (lo regenera `npm install`)
- `frontend/tsconfig.json` (`include`)
- `frontend/.gitignore`
- `frontend/vitest.config.ts` (nuevo)
- `frontend/playwright.config.ts` (nuevo)
- `frontend/tests/setup.ts` (nuevo)
- `frontend/tests/unit/http.test.ts` (nuevo)
- `frontend/tests/unit/api.test.ts` (nuevo)
- `frontend/tests/unit/components.test.tsx` (nuevo)
- `frontend/e2e/global-setup.ts` (nuevo)
- `frontend/e2e/demo.spec.ts` (nuevo)

## Dependencias externas (verificadas el 2026-10-04 en el registro de npm y en este equipo)
`devDependencies` nuevas, versiones exactas: `vitest` 5.0.3, `jsdom` 30.1.2, `@testing-library/react` 16.3.3,
`@testing-library/dom` 10.4.2, `@testing-library/user-event` 14.6.7, `@testing-library/jest-dom` 7.0.1,
`@playwright/test` 1.63.0.
- `vite` pasa de 8.0.5 a **8.0.16**: `npm audit` (incluidas las de desarrollo) marca 8.0.0–8.0.15 con una vulnerabilidad
  alta del servidor de desarrollo (GHSA-v6wh-96g9-6wx3, GHSA-fx2h-pf6j-xcff); 8.0.16 exige el mismo Node y cumple los
  `peerDependencies` de `@vitejs/plugin-react` 6.0.1 (`^8.0.0`), `@tailwindcss/vite` 4.2.2 y Vitest 5.0.3.
- Vitest 5.0.3 admite Vite 8 y exige Node `^22.12.0 || ^24.0.0 || >=26.0.0`; `@testing-library/react` 16.3.3 pide
  `@testing-library/dom` ^10. `@testing-library/jest-dom` 7.0.1 exporta `./vitest`.
- Comprobado en este equipo (Fedora 44): `vitest run` con `environment: "jsdom"`, React 19.2.4 y Testing Library pasa;
  `npx playwright install chromium` descarga la build de respaldo para Ubuntu 24.04 (avisa de SO no soportado) y un test
  de Chromium pasa.
- Scripts nuevos en `package.json`: `"test": "vitest run"`, `"e2e": "npm run build && playwright test"`. Los existentes
  no cambian.

## Comportamiento esperado

### 1. Configuración
- `vitest.config.ts`: `export default mergeConfig(viteConfig, defineConfig({ test: { environment: "jsdom", include: ["tests/unit/**/*.test.{ts,tsx}"], setupFiles: ["tests/setup.ts"], restoreMocks: true } }))`
  con `defineConfig` y `mergeConfig` de `vitest/config` y `viteConfig` importado de `./vite.config`.
- `tests/setup.ts`: `import "@testing-library/jest-dom/vitest"` y `afterEach(cleanup)` (de `@testing-library/react`).
- `tsconfig.json`: `include` pasa a `["src", "tests", "e2e", "vite.config.ts", "vitest.config.ts", "playwright.config.ts"]`
  y `compilerOptions.types` a `["node", "@testing-library/jest-dom/vitest"]`. `npm run typecheck` cubre también las
  pruebas.
- `.gitignore` añade `test-results/`, `playwright-report/` y `e2e/.auth/` (contiene la cookie de sesión de la prueba;
  nunca se versiona).
- `playwright.config.ts`: `testDir: "e2e"`, `fullyParallel: false`, `workers: 1`, `retries: 0`, `timeout: 30_000`,
  `reporter: "line"`, `globalSetup: "./e2e/global-setup.ts"`,
  `use: { baseURL: E2E_BASE, storageState: "e2e/.auth/state.json", trace: "off" }`,
  `projects: [{ name: "chromium", use: { browserName: "chromium" } }]`, con
  `const E2E_PORT = Number(process.env.LECTOR_E2E_PORT ?? "8799")` y `const E2E_BASE = "http://127.0.0.1:" + E2E_PORT`
  exportadas.

### 2. `e2e/global-setup.ts`
`export default async function globalSetup(): Promise<() => Promise<void>>`:
1. Lanza con `child_process.spawn` el comando `uv run lector-web --demo --no-browser --port <E2E_PORT>` con
   `cwd` = la raíz del repositorio (`path.resolve(__dirname, "..", "..")`, con `const __dirname = path.dirname(fileURLToPath(import.meta.url))` porque el paquete es ESM) y `stdio: ["ignore", "pipe", "pipe"]`.
2. Lee `stdout` hasta encontrar una línea que empiece por `Abra: ` (máximo 30 s; si no, mata el proceso y lanza
   `Error("lector-web no arrancó")` con lo leído de `stderr`). La URL es el resto de la línea.
3. Abre Chromium (`chromium.launch()`), un contexto nuevo, navega a esa URL (canjea el token y fija la cookie), guarda
   `context.storageState({ path: "e2e/.auth/state.json" })` y cierra el navegador.
4. Devuelve una función de cierre que envía `SIGINT` al proceso, espera a que termine (máximo 10 s; si no, `SIGKILL`) y
   borra `e2e/.auth/state.json`. Al terminar `lector-web --demo` se borra su carpeta temporal (spec 069).

### 3. Pruebas unitarias (`tests/unit/`)
`fetch` y `EventSource` se sustituyen con `vi.stubGlobal`; ninguna prueba usa red.

`http.test.ts`:
- `qs omite vacíos`: `qs({a: 1, b: null, c: undefined, d: ""})` es `"?a=1"`; `qs({})` es `""`.
- `getJson devuelve el JSON`: con `fetch` que responde 200 `{"x": 1}`, devuelve `{x: 1}` y se llamó con
  `credentials: "same-origin"`.
- `ApiError con detail`: respuesta 404 `{"detail": "avistamiento no encontrado"}` → `ApiError` con `status` 404 y
  `detail` igual; respuesta 500 sin JSON → `detail` `"error 500"`.
- `postJson envía JSON`: método `POST`, cabecera `Content-Type: application/json` y cuerpo `"{}"` sin argumento.

`api.test.ts` (sobre `src/api/index.ts`):
- `listProfiles mapea campos`: `[{name: "patrulla", label: "Patrulla", description: "d", mode: "movil", default: false}]`
  → `[{id: "patrulla", title: "Patrulla", description: "d", mode: "movil", isDefault: false}]`.
- `listSightings construye la consulta`: con `{tab: "unverified", query: " abc-1 ", runId: 3}` se pide
  `/api/sightings?q=ABC1&run=3&status=unverified&hidden=false&page=1` (el orden de los parámetros puede variar: se
  comparan como `URLSearchParams`) y `/api/sighting-counts?q=ABC1&run=3`; con `tab: "hidden"`, `hidden=true` y sin
  `status`.
- `getMetrics sin datos`: `/api/metrics` responde 404 → las cuatro `Stat` con `value: null`, `sub: "Sin datos todavía"`
  y `perVideo: []`.
- `exportCsv devuelve el nombre`: `/api/export` responde `{"file": "x.csv"}` → `"x.csv"`; el cuerpo enviado con
  `"all"` es `{"status": null}`.
- `subscribeRunProgress mapea eventos`: con un `EventSource` falso que emite `progress` con
  `{positionMs: 1000, durationMs: 20000, fraction: 0.05, sightingsSaved: 2}` el callback recibe
  `{type: "progress", processedMs: 1000, durationMs: 20000, fraction: 0.05, plates: 2}` (más `speedFactor`); un `done`
  con `state: "cancelled"` da `{type: "cancelled"}` y cierra el `EventSource`.

`components.test.tsx`:
- `SightingCard sin recorte`: con `cropUrl: null` muestra el texto `Sin recorte` y ningún `img`.
- `ReviewPanel acciones`: al pulsar "Es correcta" llama a `onDecide({action: "confirm"})`; al pulsar "Ir al video"
  llama a `onView("video")`; muestra `aparece en 0:42` para `firstSeenMs: 42_000`.
- `FrameViewer sin video`: con `<video>` que dispara `error`, muestra `El video original no está disponible`.
  (`HTMLDialogElement.prototype.showModal` se sustituye por un `vi.fn()` porque jsdom no lo implementa.)

### 4. Pruebas de punta a punta (`e2e/demo.spec.ts`)
`test.describe.configure({ mode: "serial" })`: comparten la BD de la demo y se ejecutan en este orden. En cada prueba
se registran los mensajes de consola de tipo `error` y, al final, ninguno contiene `Content Security Policy` ni
`Refused to`.
1. `revisar con el teclado`: en `/`, pulsar "Lecturas"; la pestaña "Por revisar" muestra `15`; la cabecera muestra
   `15 por revisar`; con la primera tarjeta seleccionada, pulsar `c`; la pestaña pasa a `14` y la cabecera a
   `14 por revisar`.
2. `corregir una placa`: en "Por revisar", pulsar `e`, escribir `XYZ987` y `Enter`; la pestaña "Corregidas" pasa de
   `5` a `6`.
3. `ir al video sin archivo`: con una tarjeta seleccionada, pulsar `v`; el diálogo muestra
   `El video original no está disponible` (los videos de la demo no son videos reales); `Escape` lo cierra.
4. `procesar un video de demo`: en "Procesar", elegir `demo_entrada.mp4` y "Parqueadero o entrada", pulsar
   "Procesar"; aparece "Resultado" en menos de 20 s y el botón "Revisar … placas".
5. `metricas y ajustes`: "Métricas" muestra las cuatro tarjetas; en "Ajustes", "Exportar CSV" muestra un texto que
   empieza por `Exportado a data/exports/`.

## Casos borde y manejo de errores
- Puerto 8799 ocupado: la prueba falla en el arranque con el mensaje de `lector-web`; se usa `LECTOR_E2E_PORT` para
  otro puerto.
- Si `uv` no está en el `PATH`, `global-setup` falla con el error de `spawn`; no se instala nada.

## Fuera de alcance
- Integración continua. Pruebas visuales por captura. Navegadores distintos de Chromium.

## Definition of Done
- [ ] En `frontend/`: `npm install` (regenera el lock; si cambia alguna versión directa ya fijada, **detente y
      reporta**), `npm ci`, `npm run typecheck`, `npm test` y `npm run build` en verde.
- [ ] `npx playwright install chromium` y `npm run e2e` en verde (pegar el resumen de `line`).
- [ ] `npm audit` (también dependencias de desarrollo) sin vulnerabilidades altas o críticas.
- [ ] `uv run pytest -q` (incluye `test_frontend_policy.py`), `uv run ruff check .`, `uv run ruff format --check .` y
      `uv run mypy src` limpios.
