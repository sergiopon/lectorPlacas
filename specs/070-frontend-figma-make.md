# 070 - Frontend: importar el diseño de Figma Make y conectarlo a la API real

## Objetivo
Llevar a `frontend/` la exportación de Figma Make del usuario (2026-10-04; React 19 + Vite 8 + Tailwind 4), quitarle todo
lo propio de Figma Make (plugins, analítica, carpeta `.figma`) y sustituir los datos de muestra por un cliente de la API
real de las specs 066, 067 y 076. Se conservan componentes, estilos y comportamiento de las pantallas; solo cambian los
puntos indicados aquí. Al terminar, `npm ci && npm run build` en `frontend/` genera `frontend/dist/`, que `lector-web`
sirve (spec 068).

## Depende de
066, 067, 068, 069, 076.

## Archivos rectores aplicables
- ADR-016; reglas-seguridad.md SEG-07, SEG-08, SEG-28 (sin CDN, sin telemetría, sin fuentes remotas).
- docs/08 §4.5 (comprobaciones antes de integrar), §4.6 (pantallas).
- Términos de Figma AI (versión del 2026-06-24, sección 2): el cliente conserva todos los derechos sobre el Output; no
  hay restricciones de licencia. El código se publica bajo la licencia del repo.

## Archivos a crear/modificar
El orquestador copia antes la exportación (carpeta `front/` del repo principal, sin versionar) a `frontend/` en el
worktree. Partiendo de esa copia:
- Borrar: `frontend/.figma/`, `frontend/AGENTS.md`, `frontend/CLAUDE.md`, `frontend/.mise.toml`,
  `frontend/.gitattributes`, `frontend/pnpm-lock.yaml`, `frontend/src/api/mock.ts`.
- Crear: `frontend/.nvmrc`, `frontend/package-lock.json` (lo genera `npm install`), `frontend/src/api/http.ts`.
- Modificar: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/index.html`, `frontend/tsconfig.json`,
  `frontend/.gitignore`, `frontend/src/api/index.ts`, `frontend/src/api/types.ts`, `frontend/src/lib/format.ts`,
  `frontend/src/App.tsx`, `frontend/src/screens/Procesar.tsx`, `frontend/src/screens/Lecturas.tsx`,
  `frontend/src/screens/Metricas.tsx`, `frontend/src/screens/Historial.tsx`, `frontend/src/screens/Ajustes.tsx`,
  `frontend/src/components/FrameViewer.tsx`, `frontend/src/components/ReviewPanel.tsx`,
  `frontend/src/components/SightingCard.tsx`.
- Python: `tests/unit/web/test_frontend_policy.py` (nuevo).

No se toca ningún archivo de `src/`.

## Dependencias externas (verificadas en el registro de npm el 2026-10-04)
`frontend/package.json` con versiones **exactas** (sin `^` ni `~`), las que resolvió el lockfile de la exportación:
- `dependencies`: `react` 19.2.4, `react-dom` 19.2.4.
- `devDependencies`: `@tailwindcss/vite` 4.2.2, `tailwindcss` 4.2.2, `@types/node` 22.19.17, `@types/react` 19.2.14,
  `@types/react-dom` 19.2.3, `@vitejs/plugin-react` 6.0.1, `typescript` 5.9.3, `vite` 8.0.5.
- Se elimina `oxfmt` y el script `format`.
- `"name": "lector-placas-frontend"`, `"private": true`, `"type": "module"`, `"engines": {"node": ">=22.12.0"}` (Vite
  8.0.5 exige `^20.19.0 || >=22.12.0`), scripts exactamente: `"dev": "vite"`, `"build": "tsc --noEmit && vite build"`,
  `"typecheck": "tsc --noEmit"`.
- `frontend/.nvmrc`: `22`.
- Gestor: **npm** (viene con Node). `npm install` genera `package-lock.json`; después `npm ci` debe funcionar.
  Si `npm install` resuelve una versión distinta de una dependencia directa, **detente y reporta**.

## Comportamiento esperado

### 1. Limpieza de Figma Make
- `vite.config.ts` queda con: `plugins: [react(), tailwindcss()]`; alias `@` → `./src`; `build.sourcemap: false`;
  `server: { host: "127.0.0.1", port: 5173, strictPort: true, proxy }` con `proxy` que reenvía `/api` y `/auth` a
  `process.env.LECTOR_WEB_URL ?? "http://127.0.0.1:8765"` con `changeOrigin: true`. Se borran el import de
  `.figma/make/site.json`, las funciones `figmaSiteConfiguration`, `figmaErrorOverlayReplay`,
  `figmaReactRefreshBoundaryFallback`, `figmaMakeKitPlugin`, todo lo de Google Analytics/`googletagmanager`, `base` con
  `FIGMA_PUBLIC_URL` y el bloque `preview`.
- `index.html`: `<html lang="es">`, `<title>lectorPlacas</title>`, sin los comentarios `<!-- figma:… -->`; el resto
  igual.
- `tsconfig.json`: `"include": ["src", "vite.config.ts"]` se mantiene; se añaden `"noUnusedLocals": true` y
  `"noUnusedParameters": true`.
- `.gitignore` de `frontend/`: `node_modules/`, `dist/`, `*.tsbuildinfo`, `.vite/`.

### 2. Cliente HTTP (`src/api/http.ts`)
- `export class ApiError extends Error` con `status: number` y `detail: string` (mensaje = `detail`).
- `export async function getJson<T>(path: string): Promise<T>` y
  `export async function postJson<T>(path: string, body?: unknown): Promise<T>`: `fetch(path, { credentials: "same-origin" })`
  (POST con `method: "POST"`, `headers: {"Content-Type": "application/json"}`, `body: JSON.stringify(body ?? {})`). Si
  `!res.ok`: lee `{detail}` del JSON (si no se puede, `detail = "error " + status`) y lanza `ApiError`. Si no, devuelve
  `res.json()`.
- `export function qs(params: Record<string, string | number | boolean | null | undefined>): string`: omite
  `null`/`undefined`/`""` y devuelve `""` o `"?" + URLSearchParams(...)`.
- Ningún componente llama a `fetch` ni construye URLs de la API: todo pasa por `src/api/`.

### 3. Tipos (`src/api/types.ts`), alineados con la API (JSON en camelCase)
Cambios respecto a la exportación (el resto igual):
- `Video { name: string; path: string; durationMs: number | null; sizeBytes: number }`.
- `Profile { id: string; mode: "estatico" | "movil"; title: string; description: string; isDefault: boolean }`.
- `Run { id: number; video: string; profile: string; mode: "estatico" | "movil" | null; startedAt: string;
  durationMs: number | null; speedFactor: number | null; vehicles: number | null; confirmed: number | null;
  unverified: number | null; status: "running" | "completed" | "failed" }`.
- `Sighting`: `cropUrl: string | null`; se añade `duplicateOf: number | null`.
- `SightingList { items: Sighting[]; total: number; counts: Record<SightingTab, number> }`.
- `RunEvent` =
  `{ type: "progress"; fraction: number | null; processedMs: number; durationMs: number | null; plates: number; speedFactor: number | null }`
  | `{ type: "done"; summary: RunSummary }` | `{ type: "cancelled" }` | `{ type: "failed"; message: string }`.
- `StartedJob { jobId: string; durationMs: number | null }`.
- `Stat { value: number | null; sub: string }` y
  `Metrics { auditedAccuracy: Stat; fullPlateReads: Stat; charErrorRate: Stat; autoConfirmRate: Stat; perVideo: RunMetrics[] }`
  con `RunMetrics { runId: number; video: string; legible: number; illegible: number; rejected: number; accuracy: number | null; cer: number | null }`.
- `Settings { cropRetentionDays: number; logRetentionDays: number }` (sin cambios).
- `SightingFrame { frameUrl: string; timestampMs: number }` (sin `box`).
- `VideoSource { url: string; name: string }`.
- `PurgeResult { crops: number; sightings: number; runs: number; exports: number }`.

### 4. Funciones de `src/api/index.ts` (mismos nombres que la exportación salvo donde se indica)
`onDataChange(fn)` se conserva tal cual y `decide`, `startRun` (al terminar) y `purgeExpired` llaman a `changed()`.
| Función | Implementación |
|---|---|
| `listVideos()` | `GET /api/videos` → `Video[]` tal cual. |
| `listProfiles()` | `GET /api/profiles` → cada `{name, label, description, mode, default}` a `{id: name, title: label, description, mode, isDefault: default}`. |
| `listRuns()` | `GET /api/runs?page=1,2,…` hasta una página con menos de 50 elementos; concatena; ordena por `startedAt` descendente. |
| `listSightings(f, page = 1)` | Parámetros: `q` = `f.query` en mayúsculas sin caracteres fuera de `A-Z0-9`, recortado a 10, omitido si queda vacío; `run` = `f.runId`; según `f.tab`: un estado → `status=<estado>&hidden=false`; `all` → `hidden=false`; `hidden` → `hidden=true`. Pide en paralelo `GET /api/sightings{qs}` (con `page`) y `GET /api/sighting-counts{qs}` (solo `q` y `run`). Devuelve `{items, total, counts}` con `counts` = la respuesta de conteos. |
| `getSighting(id)` | `GET /api/sightings/{id}`; `ApiError` 404 → `null`. |
| `getPendingCount()` | `GET /api/summary` → `pending`. |
| `decide(id, d)` | `POST /api/sightings/{id}/decision` con `{action, correctedText}` (`correctedText` solo con `correct`). |
| `startRun(video: Video, profile: string)` → `Promise<StartedJob>` | `POST /api/jobs` con `{video: video.path, profile}` → `{jobId, durationMs: video.durationMs}`. |
| `subscribeRunProgress(jobId, onEvent)` | `new EventSource("/api/jobs/" + jobId + "/events")`. Evento `progress` (JSON de `JobOut`): `processedMs = positionMs ?? 0`, `durationMs`, `fraction`, `plates = sightingsSaved ?? 0`, `speedFactor = processedMs / (Date.now() - inicio)` si han pasado más de 1000 ms, si no `null` (`inicio` = momento de la suscripción). Evento `done`: cierra el `EventSource`; según `state`: `completed` → pide `GET /api/sighting-counts?run=<runId>` y `GET /api/runs` (página 1, busca `runId`) y emite `done` con `RunSummary { runId, legible: unverified + confirmed, unverified, hiddenLowQuality: hidden, autoConfirmed: confirmed, durationMs: run.durationMs ?? 0 }` y llama a `changed()`; `cancelled` → `{type: "cancelled"}`; `failed` → `{type: "failed", message: message ?? "Error al procesar"}`. Error del `EventSource` → cierra y emite `failed` con `"Se perdió la conexión con el servidor"`. Devuelve una función que cierra el `EventSource`. |
| `cancelRun(jobId)` | `POST /api/jobs/{jobId}/cancel`. |
| `getMetrics()` | `GET /api/metrics` y `GET /api/metrics/runs` y `listRuns()`. `ApiError` 404 en `/api/metrics` (sin avistamientos) → todas las `Stat` con `value: null` y `sub: "Sin datos todavía"`, `perVideo: []`. Si no, con `m` = métricas: `auditedAccuracy = {value: m.precisionConfirmed, sub: m.confirmedKept + " de " + m.confirmedAudited}`; `fullPlateReads = {value: m.exactMatchRate, sub: m.reviewedReadings + " lecturas revisadas"}`; `charErrorRate = {value: m.cer, sub: m.reviewedReadings + " lecturas revisadas"}`; `autoConfirmRate = {value: total > 0 ? m.confirmedTotal / total : null, sub: m.confirmedTotal + " de " + total}` con `total = m.confirmedTotal + m.unverifiedTotal`; `perVideo` = cada `RunMetricsOut` con `video` = el `video` de su corrida (o `"Video " + runId`) y `accuracy = precision`. |
| `getSettings()` | `GET /api/settings` → `{cropRetentionDays: cropsDays, logRetentionDays: recordsDays}`. |
| `exportCsv(status)` → `Promise<string>` | `POST /api/export` con `{status: status === "all" ? null : status}` → devuelve `file`. **No descarga nada** (SEG-08: el CSV solo vive en `data/exports/`). |
| `purgeExpired()` → `Promise<PurgeResult>` | `POST /api/purge` → `{crops: cropsDeleted, sightings: sightingsDeleted, runs: runsDeleted, exports: exportsDeleted}`. |
| `getSightingFrame(id)` | Sin red: `{frameUrl: "/api/sightings/" + id + "/frame", timestampMs: Math.floor((s.firstSeenMs + s.lastSeenMs) / 2)}`; firma nueva `getSightingFrame(s: Sighting): SightingFrame` (síncrona). |
| `getVideoSource(run)` | Sin red: `{url: "/api/runs/" + run.id + "/video", name: run.video}`; firma nueva `getVideoSource(runId: number, name: string): VideoSource` (síncrona). |

### 5. Pantallas y componentes (solo estos cambios)
- **Procesar**: la lista usa `v.path` como valor seleccionado y llama a `startRun(<el Video seleccionado>, profile)`; muestra
  `v.durationMs === null ? "—" : fmtTime(v.durationMs)`. El perfil inicial es el `id` del perfil con `isDefault` (o el
  primero) cuando llegan los perfiles. Guarda `jobId` en vez de `runId`; `cancelRun(jobId)`. Las tres cifras en vivo son
  `Placas leídas` (`plates`), `Velocidad` (`speedFactor` o `—`) y `Avance` (`fraction` como porcentaje con `fmtPct` o
  `—`); se quita `Vehículos`. La barra usa `fraction` (0 si es `null`). El texto de tiempo muestra
  `fmtTime(processedMs)` y, si `durationMs` no es `null`, ` / fmtTime(durationMs)`. Con `failed`, un aviso
  `role="alert"` con el mensaje y el botón vuelve a estar disponible.
- **Lecturas**: el selector de video muestra `r.video` (sin anteponer "Video N ·"). Si `items.length < total`, al final
  de la cuadrícula un botón "Cargar más" que pide la página siguiente y concatena. La pestaña "Ocultas" usa
  `counts.hidden`.
- **SightingCard** y **ReviewPanel**: si `cropUrl` es `null`, en lugar de `<img>` un bloque `aspect-[3/1]` con el texto
  "Sin recorte". ReviewPanel no cambia sus botones (Ir al video `V`, Captura completa `F`).
- **FrameViewer**: usa las firmas síncronas nuevas. Vista "Captura completa": `<img src={frameUrl}>` sin recuadro y sin
  el enlace "Descargar captura" (SEG-07); si la imagen falla (`onError`), el mismo bloque de "no disponible" que el video,
  con el texto "El fotograma no está disponible". Vista "Video": `<video src={url} controls autoPlay
  onLoadedMetadata={seek}>`, con `seek` igual que en la exportación (un segundo antes de `firstSeenMs`); si el video
  falla (`onError`), se muestra el bloque "El video original no está disponible" de la exportación.
- **Historial**: valores `null` se muestran como `—`; el estado usa solo `running`, `completed`, `failed`.
- **Métricas**: cada `Stat` muestra `value === null ? "—" : fmtPct(value, 1)` y `sub`. Con `perVideo` vacío, en lugar de
  los dos gráficos un texto "Aún no hay lecturas revisadas por video.". En `Lines`, los puntos con `accuracy` o `cer`
  `null` se omiten de su serie; si una serie queda con menos de 2 puntos, no se dibuja su línea.
- **Ajustes**: "Exportar CSV" llama a `exportCsv` y muestra `role="status"` con
  `Exportado a data/exports/<file>`; el texto de la tarjeta pasa a "Guarda las lecturas en un archivo CSV dentro de
  data/exports/.". La purga muestra `Purga completada: <crops> recortes, <sightings> lecturas, <runs> corridas y <exports> exportaciones eliminados.`
- **format.ts**: `reasonText` añade `predicted_illegible: "Parece borrosa (filtro automático)"` y
  `predicted_not_plate: "Parece que no es una placa (filtro automático)"`; `fmtTime` admite `number` y no cambia.

### 6. Política del frontend (`tests/unit/web/test_frontend_policy.py`, Python, sin Node)
Comprueba sobre los archivos versionados de `frontend/` (excluyendo `node_modules/` y `dist/`):
- `test_no_figma_artifacts`: no existen `.figma/`, `AGENTS.md`, `pnpm-lock.yaml`, `src/api/mock.ts`; `vite.config.ts`
  no contiene `figma`, `googletagmanager`, `gtag` ni `0.0.0.0`.
- `test_no_remote_resources`: ningún archivo de `src/` ni `index.html` contiene `http://` o `https://` salvo
  `http://www.w3.org/` (espacios de nombres SVG).
- `test_exact_versions`: en `package.json`, ninguna versión de `dependencies`/`devDependencies` empieza por `^` o `~`,
  y `engines.node == ">=22.12.0"`.
- `test_api_is_single_entry`: ningún archivo de `src/` fuera de `src/api/` contiene `fetch(` ni `EventSource(`.

## Casos borde y manejo de errores
- Sin backend (p. ej. `npm run dev` sin `lector-web`): las llamadas fallan con `ApiError`; las pantallas no se rompen
  (cada `useEffect` captura el error y deja el estado vacío).
- El navegador envía la cookie de sesión en `<img>`, `<video>` y `EventSource` porque todo es del mismo origen.

## Tests de aceptación (en prosa)
Los cuatro tests de §6. Las pruebas de componentes (Vitest) y E2E (Playwright contra `lector-web --demo`) son de la
spec 071.

## Fuera de alcance
- Vitest/Playwright (071). Publicación y capturas (072). Recuadro de la placa en el fotograma (spec futura).

## Definition of Done
- [ ] En `frontend/`: `npm install` (genera el lock), después `npm ci`, `npm run typecheck` y `npm run build` sin
      errores; `frontend/dist/index.html` existe.
- [ ] `npm audit --omit=dev` sin vulnerabilidades altas o críticas (pegar el resumen).
- [ ] `uv run pytest -q` (suite completa) en verde, incluidos los 4 tests nuevos.
- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy src` limpios.
- [ ] Prueba manual del orquestador: `uv run lector-web --demo --no-browser`, abrir la URL y recorrer las cinco
      pantallas.
