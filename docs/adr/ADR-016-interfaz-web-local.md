# ADR-016 — Interfaz web local (sustituye a la GUI PySide6)

- Estado: **Aprobado** (2026-09-27, decisiones del usuario en docs/08 §6; redactado 2026-10-03). Sustituye a ADR-015
  cuando la spec 073 retire la GUI.
- Requisitos afectados: RF-28, RF-36 (pasa a cumplirse con la web), RF-33, §7 (UI web deja de estar fuera de alcance,
  solo en loopback); SEG-20, nueva SEG-28.

## Contexto
ADR-015 evaluó la "Opción 1: web local" y eligió PySide6. El usuario decidió (2026-09-27) llevar la interfaz a la web,
diseñada en Figma Make (que solo diseña) y compilada con Node, y retirar la app de escritorio cuando la web la iguale.

Verificado en el JSON de PyPI el 2026-10-03:

| Paquete | Versión | Licencia | Nota |
|---|---|---|---|
| fastapi | **0.141.1** (2026-07-29) | MIT | Desde **0.142.0** (2026-09-29) exige `opentelemetry-api>=1.44.0` como dependencia obligatoria. Se fija 0.141.1 para no meter una API de telemetría en el runtime. |
| uvicorn | 0.54.0 | BSD-3-Clause | Dependencias: `click`, `h11`. Sin extras `standard`. |
| starlette | 1.7.0 (transitiva) | BSD-3-Clause | FastAPI 0.141.1 pide `starlette>=0.46.0`. Probado el 2026-10-03 con las ruedas oficiales: rutas `async`, middleware HTTP, `lifespan` (en el mismo hilo que las peticiones) y `StreamingResponse` funcionan. |
| httpx2 | 2.13.1 (solo dev) | BSD-3-Clause | Lo usa `fastapi.testclient.TestClient`; con `httpx` 0.28.1 Starlette 1.7 emite `StarletteDeprecationWarning`. Arrastra `httpcore2` 2.13.1 (BSD-3-Clause) y `truststore` 0.10.4 (MIT). |

## Decisión
1. **Capa `web`** (`src/lector_placas/web/`): tercer composition root. Nadie la importa; de `cli` solo importa
   `lector_placas.cli.composition`; no importa `gui`. `fastapi`, `starlette` y `uvicorn` solo se importan en `web`.
2. **Script `lector-web`** (`lector_placas.web.app:main`), análogo a `lector-gui`: `os.umask(0o077)`, configuración,
   logging, clave maestra leída **antes** de `block_network()`, guardia de red activa siempre.
3. **Servidor:** Uvicorn programático, `host="127.0.0.1"`, un solo proceso, sin `--reload` ni workers, `access_log=False`.
   `block_network()` no se relaja: el servidor usa `bind`/`accept`, no `connect`.
4. **Un solo hilo para la BD de la sesión:** todos los endpoints son `async def` y usan la conexión SQLCipher abierta en
   el `lifespan` de la app (mismo hilo del bucle de eventos). El procesamiento corre en un `threading.Thread` con **su
   propia** conexión, como en la GUI.
5. **Autenticación local:** `lector-web` genera un **token de arranque** de un solo uso y abre el navegador en
   `/auth?token=…`; ese endpoint lo canjea por una **cookie de sesión** aleatoria (`HttpOnly`, `SameSite=Strict`,
   `Path=/`) y redirige a `/`. Toda ruta `/api/*` exige la cookie. Se comprueba la cabecera `Host`.
6. **Progreso:** Server-Sent Events; cancelación con `POST`.
7. **Frontend:** `frontend/` (Vite + React + TypeScript), compilado a `frontend/dist/` y servido por FastAPI como
   archivos estáticos. Node solo se necesita para compilar.
8. **Modo demo** (`lector-web --demo`): BD temporal con datos sintéticos; nunca toca `data/`.

## Alternativas descartadas
| Alternativa | Motivo |
|---|---|
| FastAPI ≥ 0.142 | Dependencia obligatoria de `opentelemetry-api`; el proyecto no admite telemetría. |
| Endpoints síncronos (`def`) | FastAPI los ejecuta en un pool de hilos y compartirían la conexión SQLCipher entre hilos. |
| Token en cada URL o en `localStorage` | Queda en el historial o al alcance de JavaScript; la cookie `HttpOnly` no. |
| WebSocket para el progreso | SSE basta (un solo sentido) y no necesita dependencias. |
| Bind a `0.0.0.0` | Expone placas a la red local. Solo se admite dentro de Docker (spec 075, excepción de SEG-28). |

## Consecuencias
- (+) Una interfaz moderna, la misma en cualquier sistema; la GUI PySide6 se retira (spec 073).
- (−) Se añade Node.js como requisito para compilar el frontend (decisión del usuario) y una superficie HTTP local que
  SEG-28 acota.
- (−) Las llamadas a la BD bloquean el bucle de eventos mientras duran; aceptable para un solo operador local.
