# 08 - Plan: solo placas legibles, más desempeño e interfaz web

Estado: aprobado con decisiones del usuario (2026-09-27, §6). Continúa `docs/historial/07-plan-mejora-lectura.md`. Cada bloque de código se especifica en su
spec (055 en adelante) y se implementa con el ciclo habitual: spec, rama `feature/NNN-*`, compuertas, revisión y merge.

> **Contrato vigente de la API:** specs 066 y 067 (rutas y campos exactos); esta tabla es el plan original.
> El comando es el script `lector-web` (spec 068), no un subcomando de `lector`.
>
> **Renumeración (2026-10-03).** El nuevo enfoque (solo placas cercanas y legibles; modos de cámara estática y móvil,
> `docs/historial/09-enfoque-versatil.md`, ADR-017) añade las specs 056 (modos de cámara), 057 (filtro de cercanía), 058 (evaluación
> con cercanía) y 061 (duplicados) y desplaza las demás. Los números de este documento ya están actualizados. Equivalencia
> con la numeración anterior: 056→059, 057→062, 058→063, 059→064, 061→065, 062–069→066–073, 070–071→074–075; la 060 se
> mantiene y se redefine. Donde este plan diga "legibles", ahora significa "legibles y cercanas" (docs/historial/09 §4.2).

Objetivos pedidos por el usuario:
1. **No mostrar placas borrosas**: que la revisión muestre solo placas que se pueden leer.
2. **Mejorar el desempeño** del programa.
3. **Interfaz web atractiva** (aunque sea en `localhost`), con la UI hecha en **Figma Make** (React + TypeScript) y
   conectada al proyecto.

---

## 1. Punto de partida (datos medidos)

| Hecho | Cifra | Fuente |
|---|---|---|
| Avistamientos revisados a mano | 1 113: 329 legibles, **422 borrosos**, 362 no-placa | CSV exportado el 2026-09-28 |
| Video de 17 min (720p, `calle_rapida`) | 45 % borrosas, 30 % no-placa, 25 % legibles; 5,5 % confirmadas solas | corrida 23 |
| CER del OCR | 3,7 % en el test; 12–14 % en video real | ADR-014, docs/historial/07 |
| Precisión de las confirmadas automáticas | 93 % (57/61), meta 98 % | `review --status confirmed` |
| Velocidad | 0,85× tiempo real (meta ≥ 1×) | corrida 23 |
| Reentrenos del OCR con datos propios | 2 intentos, empate con v1 | docs/historial/07 Fase 4 |

Conclusión: **3 de cada 4 avistamientos que el usuario revisa no aportan nada** (borrosos o no-placa). El mayor salto
de calidad percibida no está en el OCR, sino en **no enseñar lo inservible** y en **capturar mejor imagen**.

---

## 2. Solo placas legibles

### 2.1 Idea

Hoy el sistema detecta, lee y deja "por revisar" todo lo dudoso, y el usuario marca a mano 422 borrosas. Se propone
un **filtro de legibilidad** que prediga, para cada avistamiento, si su mejor recorte es:
- **legible**,
- **borroso** (es placa, no se lee) o
- **no-placa**.

Lo que se predice borroso o no-placa **no se borra**: queda `unverified` con una razón nueva y fuera de la vista
principal, con una pestaña para auditarlo ("Ocultas por baja calidad (N)"). Así se cumple "no me muestres las borrosas"
sin perder precisión: si el filtro se equivoca, se puede recuperar. Las métricas miden cuántas legibles se esconden
por error.

### 2.2 Los datos ya existen, pero caducan

Las 1 113 etiquetas humanas son justo el dataset que hace falta, pero los recortes cifrados se purgan por retención y
`export-reviewed` solo exporta las legibles.

**Hecho (2026-09-27, decisión del usuario):** `retention.crops_days` sube de 30 a **90 días** en `config/lector.yaml`,
como excepción temporal anotada en SEG-03. Los primeros recortes (2026-09-26) caducan ahora el **2026-12-25**, que es
también la fecha en que `records_days` = 90 borra sus avistamientos. La spec 055 debe estar exportada antes de esa
fecha. Cuando exista el dataset, se vuelve a 30 días.

### 2.3 Specs

| Spec | Qué hace | Detalle |
|---|---|---|
| **055** Exportar dataset de legibilidad | `lector dataset export-legibility` | Como `export-reviewed` (spec 035), pero exporta **todos** los revisados con su clase (`legible` / `borrosa` / `no_placa`) y sus métricas (confianza, acuerdo, nº de lecturas, tipo de vehículo, tamaño del recorte). Misma retención propia de 180 días y mismas reglas SEG-07. **Urgente.** |
| **059** Características de calidad | Guardar por avistamiento el ancho y alto de la placa en píxeles, la nitidez y el contraste del mejor recorte | Hoy la nitidez se calcula pero no se guarda (docs/historial/07 §2). Columnas nuevas: migración de esquema v2 → v3, con la misma receta que la spec 052. |
| **062** Modelo de legibilidad (entrenamiento) | En `training/legibility` (proyecto uv nuevo): primero una **regresión logística** sobre las características de 055/059 y, si no basta, una **CNN pequeña** sobre el recorte, exportada a ONNX | Reparto por vehículo y por video (como `mix_dataset`) para no filtrar datos entre splits. Se elige un umbral con el criterio del §2.4. La regresión logística se exporta como coeficientes a `config/lector.yaml`; la CNN, como ONNX verificado por hash en `config/models.yaml`. |
| **063** Filtro de legibilidad en el pipeline | Tras consolidar, calcular la puntuación; por debajo del umbral, razón nueva `PREDICTED_ILLEGIBLE` o `PREDICTED_NOT_PLATE` | Nunca confirma ni borra: solo añade una razón. Sin migración, porque `reasons` es texto (como en la 050). |
| **064** Vista "solo legibles" | En la GUI (y en la web, §4) el filtro "Por revisar" excluye por defecto las razones `PREDICTED_*`; pestaña "Ocultas por baja calidad" para auditarlas; `evaluate-review` informa cuántas ocultas eran legibles | Afecta a `readings_filters.py`, `review_metrics.py` y a la API web. |

### 2.4 Criterio de aceptación del filtro

Se mide en un split de prueba por video, nunca visto al entrenar:
- **Legibles escondidas por error ≤ 5 %** (recall de legibles ≥ 95 %). Es la condición que protege la precisión.
- Con ese umbral, **borrosas y no-placas ocultadas ≥ 60 %** (objetivo; se reporta la cifra real).
- Intervalo de confianza por bootstrap por vehículo, como en `evaluate_ocr`.

Si ningún umbral cumple la primera condición, el filtro no se activa y se reporta.

La decisión de aceptarlo la toma un revisor independiente (subagente Opus) antes de encenderlo, como cualquier
cambio que afecte a las métricas de docs/04.

---

## 3. Más desempeño

Ordenado por impacto esperado. Cada punto se mide antes y después con los mismos videos.

| # | Acción | Tipo | Por qué |
|---|---|---|---|
| 1 | **Mejor captura** | Operación, sin código | 45 % de placas ilegibles incluso para una persona. Recomendación: 1080p o más, velocidad de obturación alta (menos desenfoque de movimiento), cámara fija y cerca del paso de los vehículos, sin zoom digital, buena luz. Se documenta como guía en el README. |
| 2 | **Anotar la verdad de un tramo** (docs/historial/07 Fase 1) | Operación | Sin ground truth, M-01 a M-03 nunca se han medido. Basta un tramo de 3–5 min en 1080p. |
| 3 | **Calibrar perfiles** (docs/historial/07 Fase 2) | Configuración | Probar `target_fps` 15 frente a 30 (velocidad 0,85× → ≥ 1×), `min_readings` 2 (elimina gran parte de las no-placas de una sola lectura), `min_plate_width_px` 40/60 y el detector `yolo26n-plates`. |
| 4 | **Spec 060: parada temprana por track** | Código | La spec 051 lee cada vehículo en todos los frames, lo que es caro. Se deja de leer un track cuando sus N mejores lecturas ya coinciden con alta confianza. Recupera velocidad sin perder las lecturas cercanas. |
| 5 | **Spec 065: tipo de vehículo por la forma de la placa** | Código | El detector COCO confunde carros y motos, y eso genera dudas de formato (docs/historial/07 §1.1). La proporción de la caja de la placa distingue la placa de moto de la de carro; las dimensiones oficiales están **PENDIENTES DE VALIDAR** en la normativa (Res. 4923/1994 y la ficha técnica MT 001). |
| 6 | **Reentrenar el OCR** | Operación | Solo cuando `test_video` tenga ≥ 100 recortes (unos 500 revisados). Hasta entonces no hay forma de demostrar la mejora (docs/historial/07). |

---

## 4. Interfaz web (localhost) con Figma Make

### 4.1 Arquitectura

ADR-015 ya evaluó esta opción ("Opción 1: web local") y fijó sus condiciones de seguridad. Se redacta un **ADR-016**
que la adopta y **sustituye a la GUI PySide6** (decisión del usuario): la app de escritorio se retira (spec 073) en cuanto
la web cubra sus funciones. Así el proyecto queda con una sola interfaz gráfica, la web, más la CLI.

```
navegador (http://127.0.0.1:PUERTO)
   │  React + TypeScript (UI generada con Figma Make, compilada con Vite)
   ▼
lector-web  ──  FastAPI + Uvicorn, ligado SOLO a 127.0.0.1
   │  capa nueva `web`: tercer composition root, nadie la importa
   │  (como `gui`, solo importa `lector_placas.cli.composition`)
   ▼
casos de uso existentes: ProcessVideo, DecideSighting, ExportSightings, PurgeExpiredData, métricas…
   ▼
SQLCipher + recortes AES-GCM (sin cambios)
```

- **Backend:** FastAPI + Uvicorn. En ADR-015 se consultaron en PyPI FastAPI 0.141.1 y Uvicorn 0.54.0 (2026-09-27); la
  spec vuelve a verificar las versiones antes de fijarlas.
- **Procesamiento:** en un hilo con **su propia** conexión SQLCipher, igual que la GUI. El progreso se envía con
  **Server-Sent Events** (`/api/jobs/{jobId}/events`) y la cancelación con un `POST` (spec 067: el procesamiento es un *trabajo*; su `runId` se conoce al terminar).
- **Guardia de red:** `block_network()` solo reemplaza `connect`/`create_connection`. Un servidor que escucha en
  loopback usa `bind`/`accept`, así que la guardia **no se relaja**. Hay que verificarlo con `strace` en el nivel F: el
  proceso no debe hacer ningún `connect` saliente. Uvicorn se arranca sin `--reload` ni workers extra.
- **Frontend:** carpeta `frontend/` (Vite + React + TypeScript). En producción, FastAPI sirve el `dist/` compilado
  (sin CDN). En desarrollo, Vite con proxy a la API.

### 4.2 Seguridad (regla nueva SEG-28, basada en ADR-015)

- Bind **solo** a `127.0.0.1`; nunca `0.0.0.0`. Se comprueba `Host` contra DNS rebinding.
- **Token aleatorio por sesión**: `lector-web` lo genera, abre el navegador con él y la API lo exige en cada petición
  (cookie `HttpOnly`, `SameSite=Strict`). Protege frente a otros procesos o usuarios del equipo y frente a CSRF.
- Cabeceras: CSP estricta (sin scripts externos), `Cache-Control: no-store` en los recortes y en las respuestas con
  placas, `Referrer-Policy: no-referrer`.
- Los recortes se descifran en memoria y se sirven sin tocar el disco.
- Logs de acceso de Uvicorn sin texto de placa (rutas con IDs, nunca con placas).
- **Figma Make nunca recibe datos reales**: ni recortes, ni placas, ni capturas de videos propios. Solo el modo demo
  sintético del §4.4 (misma regla que SEG-09 para las APIs externas).

### 4.3 API (contrato primero)

La spec de la API fija un **OpenAPI** estable antes de diseñar la UI. Con él, Figma Make trabaja sobre datos con la
forma real y el cliente TypeScript se genera solo.

| Método y ruta | Uso |
|---|---|
| `GET /api/videos` | Videos disponibles en `input.allowed_dirs` |
| `GET /api/profiles` | Perfiles con su etiqueta legible |
| `POST /api/jobs` · `GET /api/jobs/{jobId}` · `GET /api/runs` | Procesar un video · estado del trabajo · historial |
| `GET /api/jobs/{jobId}/events` (SSE) · `POST /api/jobs/{jobId}/cancel` | Progreso en vivo y cancelación |
| `GET /api/sightings?status=&q=&run=&hidden=&page=` | Galería con filtros; `hidden=false` por defecto (solo legibles, §2) |
| `GET /api/sightings/{id}` · `GET /api/sightings/{id}/crop` | Detalle y recorte (PNG en memoria, `no-store`) |
| `POST /api/sightings/{id}/decision` | Confirmar / corregir / descartar / borrosa (`DecideSighting`) |
| `GET /api/metrics` · `POST /api/export` · `POST /api/purge` | Métricas de revisión, CSV, retención |

### 4.4 Modo demo sintético (para diseñar, probar y enseñar)

Spec **069**: `lector web --demo` arranca con una BD temporal llena de avistamientos **sintéticos**: placas falsas con
formato colombiano. `src/` no puede importar `training/` (son proyectos separados), así que la spec decide entre dos
opciones: generar los recortes una vez con `training/ocr/ocr_training/synthetic_plates.py` y versionarlos como
recursos de demo, o portar a `src/` un generador mínimo. Sirve para:
- darle a Figma Make datos realistas sin exponer ningún dato real;
- las pruebas end-to-end;
- **capturas y GIF del README**, y que un visitante del repo vea la app sin tener video propio.

### 4.5 Flujo con Figma Make

Reparto (decisión del usuario, 2026-09-27): **Figma Make solo diseña**, a partir del prompt del **Anexo A**. Todo lo
demás es trabajo del proyecto, con el ciclo de specs.

1. **Diseño (usuario):** pegar el prompt del Anexo A en Figma Make, iterar hasta que guste y exportar el código. Figma
   Make trabaja solo con los datos ficticios que trae el propio prompt; nunca con recortes, placas ni capturas reales.
2. **Comprobaciones antes de integrar (Claude):** formato de la exportación, versión de React y librerías que añade,
   y términos de uso del código generado, para poder publicarlo bajo AGPL-3.0. Todo esto está **NO VERIFICADO** hasta
   ver la exportación real.
3. **Integración (spec 070):** el código entra en `frontend/` en su rama. Se conservan componentes y estilos; los datos
   de muestra se sustituyen por un cliente tipado, generado a partir del OpenAPI de la API (§4.3; herramienta a
   verificar en npm, p. ej. `openapi-typescript`). Nada de `fetch` repartido por los componentes.
4. **Revisión:** accesibilidad (contraste AA, todo usable con teclado, atajos C/E/R/B/S); sin CDN ni fuentes remotas;
   sin telemetría (revisar el `package.json` exportado); `npm audit` limpio.

### 4.6 Pantallas

- **Inicio / Procesar:** arrastrar o elegir un video de `videos/`, elegir escenario con tarjetas explicativas, barra de
  progreso en vivo con contadores (vehículos, placas leídas, velocidad) y botón cancelar.
- **Galería:** cuadrícula de tarjetas con recorte grande, texto de la placa con formato colombiano (`ABC 123`),
  indicador de confianza y estado. Filtros arriba; por defecto **solo legibles por revisar**. Pestaña "Ocultas por
  baja calidad (N)".
- **Panel de revisión:** recorte ampliado, lo que leyó el sistema, por qué duda, y botones más atajos de teclado.
  Tras decidir, pasa a la siguiente.
- **Resumen de un video:** tarjetas con cifras y gráficos (legibles / borrosas / no-placa, confirmadas solas, tiempo).
- **Métricas:** evolución de la precisión auditada, CER real y tasa de confirmación a lo largo de las corridas.
- **Ajustes:** retención, exportar CSV, purgar.

### 4.7 Specs de la web

| Spec | Contenido |
|---|---|
| ADR-016 + SEG-28 | Decisión web local y reglas de seguridad (las redacta Claude) |
| **066** API de lectura | App factory, token, cabeceras, `videos`, `profiles`, `runs`, `sightings`, `crop`; tests con `TestClient` |
| **067** API de acciones | Procesar en un hilo + SSE + cancelación, decisiones, export, purga, métricas |
| **068** Comando `lector-web` | Arranque en 127.0.0.1, puerto libre, abrir el navegador con el token, servir `dist/` |
| **069** Modo demo sintético | BD temporal y recortes sintéticos; genera los JSON de muestra para Figma Make |
| **070** Importar el frontend de Figma Make | `frontend/` compilable, cliente tipado, sin datos de muestra en producción |
| **071** Pantallas conectadas y pruebas E2E | Pruebas de componentes (Vitest) y E2E (Playwright) contra el modo demo |
| **072** Publicación | README (inicio rápido con `lector-web`, capturas del modo demo), nivel F con `bind` loopback |

Herramientas nuevas que pide la web: **Node.js LTS** (decisión del usuario: se exige). El inicio rápido añade
`npm ci && npm run build` en `frontend/`; la versión de Node se fija en `frontend/.nvmrc` y en `engines` de
`package.json`. La alternativa sin Node ni uv en el equipo es **Docker** (§4.8).

| Spec | Contenido |
|---|---|
| **073** Retirar la GUI PySide6 | Solo cuando la web cubra las funciones de la GUI (§4.6): se eliminan la capa `gui`, el script `lector-gui`, la dependencia PySide6 y sus tests; ADR-015 queda sustituido por ADR-016; `ARQUITECTURA.md`, SEG-27 y README se actualizan. La ventana OpenCV de revisión de la CLI (`lector review`) se mantiene. |

### 4.8 Docker (alternativa de despliegue)

Objetivo: `docker compose up` y abrir el navegador, sin instalar uv, Python ni Node en el equipo.

- **Imagen multi-etapa:** una etapa `node` compila `frontend/`; otra etapa Python con uv instala el proyecto con
  `uv sync --locked` y copia el `dist/`. Imágenes base con versión y digest fijados, a verificar al redactar la spec.
- **Modelos:** `lector models fetch` al construir la imagen, porque es la única etapa con red, o en el primer arranque
  sobre un volumen. Siempre verificados por SHA-256.
- **Volúmenes:** `videos/` en solo lectura, `data/` y `logs/` persistentes y `config/` montado. Nada sensible dentro de
  la imagen.
- **Red:** el puerto se publica **solo en el loopback del equipo** (`127.0.0.1:PUERTO:PUERTO`). Dentro del contenedor
  el servidor tiene que escuchar en `0.0.0.0` para que Docker lo alcance; es una **excepción acotada a SEG-28** que solo
  se permite con la variable `LECTOR_IN_CONTAINER=1`. El token y la comprobación de `Host` se mantienen. La guardia de
  red sigue activa en el proceso.
- **Problema a resolver: la clave maestra.** Hoy vive en el llavero del sistema (Secret Service por D-Bus), que no
  existe dentro de un contenedor. Opción recomendada: un `KeyProvider` nuevo que lea la clave de un **Docker secret**
  (archivo montado en `/run/secrets/`, solo lectura, 0400), generado una vez por `lector key init --to-file`. Así la
  clave nunca queda en la imagen, en variables de entorno ni en los logs. Requiere actualizar SEG-02/ADR-005 (dónde
  puede vivir la clave) y lo decide la spec, con revisión de seguridad.
- **GPU:** imagen por defecto en CPU; perfil `gpu` de compose con `--gpus all`, que necesita el NVIDIA Container
  Toolkit en el equipo anfitrión. **NO VERIFICADO** que las ruedas `nvidia-*` de ONNX Runtime funcionen dentro del
  contenedor solo con el driver del anfitrión: se comprueba en la spec.

| Spec | Contenido |
|---|---|
| **074** `KeyProvider` de archivo (Docker secret) | `lector key init --to-file <ruta>` y lectura desde `/run/secrets/…` cuando se configura; tests de permisos y de que la clave nunca se registra |
| **075** Imagen y compose | `Dockerfile` multi-etapa, `compose.yaml` (perfiles `cpu`/`gpu`), volúmenes, publicación en loopback, `HEALTHCHECK`, `.dockerignore` que excluye `data/`, `videos/`, `models/`, `CLAUDE.md`, `CONTEXT.md` |


---

## 5. Orden propuesto

| Paso | Qué | Bloquea a |
|---|---|---|
| 0 | ~~Decidir la retención de recortes~~: hecho, 90 días (§2.2) | — |
| 1 | **055** exportar dataset de legibilidad (antes del 2026-12-25) | 062 |
| 2 | Anotar un tramo con verdad (docs/historial/07 Fase 1) + guía de captura | 3 |
| 3 | Calibrar perfiles (docs/historial/07 Fase 2) y **060** parada temprana | — |
| 4 | **059** → **062** → **063** → **064**: filtro de legibilidad | web (galería "solo legibles") |
| 5 | ADR-016, SEG-28, **066**, **067**, **068**, **069** (backend y demo) | 070 |
| 6 | Diseño en Figma Make con el Anexo A (usuario); integración **070** y **071** | 072 |
| 7 | **072** publicación y **065** tipo de vehículo | — |
| 8 | **073** retirar la GUI PySide6 (cuando la web la iguale) | — |
| 9 | **074** clave desde archivo y **075** Docker | — |

Los pasos 4 y 5 pueden ir en paralelo: no comparten archivos.

---

## 6. Decisiones del usuario (2026-09-27)

1. **Retención de recortes:** 90 días de forma temporal (aplicado; §2.2).
2. **Interfaz:** se lleva todo a la **web** y se **retira la app de escritorio** PySide6 (spec 073, cuando la web la
   iguale).
3. **Frontend:** se **exige Node.js** para compilarlo. Además, **Docker** como alternativa de despliegue (§4.8).
4. **Figma Make:** el plan del usuario **permite exportar el código**. Falta comprobar el formato exacto de la
   exportación y los términos de uso del código generado (§4.5 paso 2).
5. **Placas ocultas por baja calidad:** se muestran **en una pestaña aparte** ("Ocultas por baja calidad (N)"), nunca en
   la vista principal.

## 7. Criterios de "proyecto terminado"

- El inicio rápido del README lleva a la web en ≤ 6 comandos (uv + Node), o con `docker compose up`, probado desde un
  clon limpio (como el 2026-09-27).
- La app PySide6 está retirada y el proyecto tiene una sola interfaz gráfica: la web.
- `lector web --demo` enseña la app completa con datos sintéticos; las capturas del README salen de ahí.
- En la vista por defecto, **≥ 60 % menos avistamientos inservibles** que hoy, con **≤ 5 % de legibles escondidas**
  (medido, §2.4).
- Velocidad ≥ 1× en 1080p con el perfil calibrado.
- M-01 a M-03 medidos con al menos un tramo anotado; el README publica las cifras, cumplan o no la meta.
- Suite completa (Python y frontend), `ruff`, `mypy --strict`, `npm run lint`/`tsc` y nivel F en verde.

---

## Anexo A - Prompt para Figma Make

Copiar tal cual. Todos los datos son ficticios. Si Figma Make pide cambios, se ajustan aquí y no se le envía nada real.

```text
Diseña una aplicación web de escritorio (React + TypeScript, Vite) llamada "lectorPlacas": un lector de placas de
vehículos colombianos que procesa videos localmente y ayuda a una persona a revisar las lecturas dudosas. Funciona
en localhost; es una herramienta de trabajo, no una página de marketing. Idioma de la interfaz: español.

ESTILO
- Sobrio y profesional, tipo panel de análisis: mucho espacio, jerarquía clara, esquinas suaves, sombras sutiles.
- Modo claro y modo oscuro (seguir la preferencia del sistema, con selector manual).
- Color de acento azul. Colores de estado fijos: "Por revisar" ámbar, "Confirmada" verde, "Corregida" azul,
  "Descartada" rojo, "Borrosa" gris. El color nunca es la única señal: siempre acompaña un texto o un icono.
- La placa se muestra como en la vida real: fondo amarillo, texto negro grueso, formato "ABC 123" (motos: "ABC 12D").
- Tipografía del sistema (sin fuentes remotas). Contraste WCAG AA. Todo usable con teclado y foco visible.
- Pensado para pantallas de 1280 px o más; en ventanas estrechas el panel lateral pasa a ser un cajón.

ESTRUCTURA
Barra superior con el nombre, navegación (Procesar, Lecturas, Métricas, Historial, Ajustes), un contador
"N por revisar" y el selector de tema.

PANTALLA 1 - PROCESAR
- Lista de videos disponibles (nombre, duración, tamaño) con una zona para elegir uno.
- Selector de escenario con cuatro tarjetas agrupadas por modo de cámara. Cámara fija: "Parqueadero o entrada"
  (vehículos lentos o detenidos, cerca de la cámara), "Calle con tráfico lento" (tráfico urbano normal), "Vía rápida"
  (vehículos a mayor velocidad). Cámara en vehículo: "Patrulla" (la cámara se mueve con el vehículo).
- Botón principal "Procesar".
- Durante el proceso: barra de progreso, tiempo del video procesado / duración, contadores en vivo (vehículos,
  placas leídas, velocidad "1,2x tiempo real") y botón "Cancelar".
- Al terminar: resumen con tarjetas (legibles, por revisar, ocultas por baja calidad, confirmadas automáticamente,
  duración) y botón "Revisar N placas".

PANTALLA 2 - LECTURAS (la más importante)
- Arriba: filtros como pestañas con contador: "Por revisar", "Confirmadas", "Corregidas", "Descartadas",
  "Borrosas", "Todas", y una pestaña separada y discreta "Ocultas por baja calidad (N)". Buscador por placa y
  selector de video.
- Centro: cuadrícula de tarjetas. Cada tarjeta muestra el recorte de la placa (imagen apaisada, relación 3:1), la
  placa leída en formato de placa colombiana, el tipo de vehículo (carro, moto, bus, camión), una barra pequeña de
  seguridad del lector (porcentaje) y la etiqueta de estado. La tarjeta seleccionada queda resaltada.
- Derecha: panel de revisión fijo con el recorte ampliado, la placa en grande, "El sistema leyó: ABC 128" cuando
  difiere, la barra de seguridad, una lista "Por qué revisarla" con los motivos, y "Carro · aparece en 0:42–0:45 ·
  video 3". Acciones grandes con su atajo visible:
    ✓ Es correcta (C)   ✎ Corregir (E)   ✗ No es una placa (R)   ◐ Placa borrosa (B)   Saltar (S)
  "Corregir" convierte la placa en un campo de texto en mayúsculas (Enter guarda, Esc cancela). Tras decidir, se
  selecciona sola la siguiente tarjeta pendiente, con una transición suave.
- Estados vacíos amables ("No hay placas por revisar. ¡Todo al día!") y un estado de carga con esqueletos.

PANTALLA 3 - MÉTRICAS
- Tarjetas: precisión de las confirmadas auditadas, placas leídas completas, error por carácter del lector, tasa
  de confirmación automática. Cada cifra con su tamaño de muestra ("57 de 61").
- Gráfico de barras apiladas por video: legibles / borrosas / no es placa.
- Gráfico de línea de la precisión y el error a lo largo de los videos.
- Nota discreta: "Estimación a partir de la revisión humana".

PANTALLA 4 - HISTORIAL
- Tabla de videos procesados: fecha, video, escenario, duración, velocidad, vehículos, confirmadas, por revisar y
  estado (completado, cancelado, fallido), con un botón "Ver lecturas" por fila.

PANTALLA 5 - AJUSTES
- Retención (recortes 90 días, registros 90 días) con explicación breve, botón "Exportar CSV" (con filtro de
  estado) y botón "Purgar datos vencidos" con diálogo de confirmación.

REQUISITOS TÉCNICOS DEL CÓDIGO
- React + TypeScript estricto, componentes funcionales y pequeños, sin librerías de CDN ni scripts externos, sin
  analítica ni telemetría.
- Todos los datos salen de un único módulo `src/api/` con funciones asíncronas tipadas (por ejemplo
  `listSightings(filters)`, `getSighting(id)`, `decide(id, decision)`, `startRun(video, profile)`,
  `subscribeRunProgress(runId, onEvent)`, `getMetrics()`, `listRuns()`) que de momento devuelven datos de muestra.
  Ningún componente debe tener datos escritos dentro: así después se sustituye ese módulo por la API real.
- Tipos de datos (usar exactamente estos nombres de campo):
  Sighting { id: number; runId: number; vehicleType: "car" | "motorcycle" | "bus" | "truck";
    plateText: string; ocrText: string; confidence: number; agreement: number; numReadings: number;
    status: "unverified" | "confirmed" | "corrected" | "rejected" | "illegible";
    reasons: string[]; hiddenLowQuality: boolean; duplicates: number; firstSeenMs: number; lastSeenMs: number;
    cropUrl: string; reviewedAt: string | null }
  Run { id: number; video: string; profile: string; mode: "estatico" | "movil";
    startedAt: string; durationMs: number; speedFactor: number; vehicles: number; confirmed: number;
    unverified: number; status: "running" | "completed" | "failed" }
  Decision { action: "confirm" | "correct" | "reject" | "illegible"; correctedText?: string }
  Los motivos (`reasons`) se muestran con estos textos: insufficient_readings "Se leyó pocas veces";
  low_confidence "El lector no estaba seguro"; low_agreement "Las lecturas no coinciden entre sí";
  unrecognized_format "No parece una placa colombiana"; unverified_format "Formato de placa poco común";
  vehicle_format_mismatch "El formato no corresponde al tipo de vehículo"; ambiguous_format "Encaja en más de
  un formato"; correction_conflict "Podría ser otra placa: una letra o un número dudoso".
- Datos de muestra: unas 40 lecturas ficticias con placas inventadas de formato colombiano (carros "ABC123",
  motos "XYZ98K"), mezcla de estados y motivos, y 5 videos ficticios. Para los recortes usa rectángulos
  generados (placa amarilla con el texto), nunca fotos de placas reales.
- Atajos de teclado C, E, R, B, S y flechas para moverse por la cuadrícula; no deben dispararse mientras se
  escribe en un campo de texto.
```
