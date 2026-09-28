# 08 - Plan: solo placas legibles, más desempeño e interfaz web

Estado: propuesto (2026-09-27). Continúa `docs/07-plan-mejora-lectura.md`. Cada bloque de código se especifica en su
spec (055 en adelante) y se implementa con el ciclo habitual: spec, rama `feature/NNN-*`, compuertas, revisión y merge.

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
| CER del OCR | 3,7 % en el test; 12–14 % en video real | ADR-014, docs/07 |
| Precisión de las confirmadas automáticas | 93 % (57/61), meta 98 % | `review --status confirmed` |
| Velocidad | 0,85× tiempo real (meta ≥ 1×) | corrida 23 |
| Reentrenos del OCR con datos propios | 2 intentos, empate con v1 | docs/07 Fase 4 |

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

Las 1 113 etiquetas humanas son justo el dataset que hace falta. Pero los **recortes cifrados se purgan a los 30 días**
(`retention.crops_days`): los primeros caducan el **2026-10-26**, y `export-reviewed` solo exporta las legibles.

**Acción inmediata (sin código, decisión del usuario):** subir temporalmente `retention.crops_days` a 90 en
`config/lector.yaml` mientras se construye el filtro. Es un compromiso de privacidad (más tiempo con recortes guardados,
siempre cifrados), por eso lo decide el usuario. La alternativa es implementar la spec 055 antes del 26 de octubre.

### 2.3 Specs

| Spec | Qué hace | Detalle |
|---|---|---|
| **055** Exportar dataset de legibilidad | `lector dataset export-legibility` | Como `export-reviewed` (spec 035), pero exporta **todos** los revisados con su clase (`legible` / `borrosa` / `no_placa`) y sus métricas (confianza, acuerdo, nº de lecturas, tipo de vehículo, tamaño del recorte). Misma retención propia de 180 días y mismas reglas SEG-07. **Urgente.** |
| **056** Características de calidad | Guardar por avistamiento el ancho y alto de la placa en píxeles, la nitidez y el contraste del mejor recorte | Hoy la nitidez se calcula pero no se guarda (docs/07 §2). Columnas nuevas: migración de esquema v2 → v3, con la misma receta que la spec 052. |
| **057** Modelo de legibilidad (entrenamiento) | En `training/legibility` (proyecto uv nuevo): primero una **regresión logística** sobre las características de 055/056 y, si no basta, una **CNN pequeña** sobre el recorte, exportada a ONNX | Reparto por vehículo y por video (como `mix_dataset`) para no filtrar datos entre splits. Se elige un umbral con el criterio del §2.4. La regresión logística se exporta como coeficientes a `config/lector.yaml`; la CNN, como ONNX verificado por hash en `config/models.yaml`. |
| **058** Filtro de legibilidad en el pipeline | Tras consolidar, calcular la puntuación; por debajo del umbral, razón nueva `PREDICTED_ILLEGIBLE` o `PREDICTED_NOT_PLATE` | Nunca confirma ni borra: solo añade una razón. Sin migración, porque `reasons` es texto (como en la 050). |
| **059** Vista "solo legibles" | En la GUI (y en la web, §4) el filtro "Por revisar" excluye por defecto las razones `PREDICTED_*`; pestaña "Ocultas por baja calidad" para auditarlas; `evaluate-review` informa cuántas ocultas eran legibles | Afecta a `readings_filters.py`, `review_metrics.py` y a la API web. |

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
| 2 | **Anotar la verdad de un tramo** (docs/07 Fase 1) | Operación | Sin ground truth, M-01 a M-03 nunca se han medido. Basta un tramo de 3–5 min en 1080p. |
| 3 | **Calibrar perfiles** (docs/07 Fase 2) | Configuración | Probar `target_fps` 15 frente a 30 (velocidad 0,85× → ≥ 1×), `min_readings` 2 (elimina gran parte de las no-placas de una sola lectura), `min_plate_width_px` 40/60 y el detector `yolo26n-plates`. |
| 4 | **Spec 060: parada temprana por track** | Código | La spec 051 lee cada vehículo en todos los frames, lo que es caro. Se deja de leer un track cuando sus N mejores lecturas ya coinciden con alta confianza. Recupera velocidad sin perder las lecturas cercanas. |
| 5 | **Spec 061: tipo de vehículo por la forma de la placa** | Código | El detector COCO confunde carros y motos, y eso genera dudas de formato (docs/07 §1.1). La proporción de la caja de la placa distingue la placa de moto de la de carro; las dimensiones oficiales están **PENDIENTES DE VALIDAR** en la normativa (Res. 4923/1994 y la ficha técnica MT 001). |
| 6 | **Reentrenar el OCR** | Operación | Solo cuando `test_video` tenga ≥ 100 recortes (unos 500 revisados). Hasta entonces no hay forma de demostrar la mejora (docs/07). |

---

## 4. Interfaz web (localhost) con Figma Make

### 4.1 Arquitectura

ADR-015 ya evaluó esta opción ("Opción 1: web local") y fijó sus condiciones de seguridad. Se redacta un **ADR-016**
que la adopta **junto a** la GUI PySide6. La GUI no se elimina hasta que la web la iguale.

```
navegador (http://127.0.0.1:PUERTO)
   │  React + TypeScript (UI generada con Figma Make, compilada con Vite)
   ▼
lector web  ──  FastAPI + Uvicorn, ligado SOLO a 127.0.0.1
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
  **Server-Sent Events** (`/api/runs/{id}/events`) y la cancelación con un `POST`.
- **Guardia de red:** `block_network()` solo reemplaza `connect`/`create_connection`. Un servidor que escucha en
  loopback usa `bind`/`accept`, así que la guardia **no se relaja**. Hay que verificarlo con `strace` en el nivel F: el
  proceso no debe hacer ningún `connect` saliente. Uvicorn se arranca sin `--reload` ni workers extra.
- **Frontend:** carpeta `frontend/` (Vite + React + TypeScript). En producción, FastAPI sirve el `dist/` compilado
  (sin CDN). En desarrollo, Vite con proxy a la API.

### 4.2 Seguridad (regla nueva SEG-28, basada en ADR-015)

- Bind **solo** a `127.0.0.1`; nunca `0.0.0.0`. Se comprueba `Host` contra DNS rebinding.
- **Token aleatorio por sesión**: `lector web` lo genera, abre el navegador con él y la API lo exige en cada petición
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
| `POST /api/runs` · `GET /api/runs` · `GET /api/runs/{id}` | Procesar un video · historial · detalle |
| `GET /api/runs/{id}/events` (SSE) · `POST /api/runs/{id}/cancel` | Progreso en vivo y cancelación |
| `GET /api/sightings?status=&q=&run=&hidden=&page=` | Galería con filtros; `hidden=false` por defecto (solo legibles, §2) |
| `GET /api/sightings/{id}` · `GET /api/sightings/{id}/crop` | Detalle y recorte (PNG en memoria, `no-store`) |
| `POST /api/sightings/{id}/decision` | Confirmar / corregir / descartar / borrosa (`DecideSighting`) |
| `GET /api/metrics` · `POST /api/export` · `POST /api/purge` | Métricas de revisión, CSV, retención |

### 4.4 Modo demo sintético (para diseñar, probar y enseñar)

Spec **065**: `lector web --demo` arranca con una BD temporal llena de avistamientos **sintéticos**: placas falsas con
formato colombiano. `src/` no puede importar `training/` (son proyectos separados), así que la spec decide entre dos
opciones: generar los recortes una vez con `training/ocr/ocr_training/synthetic_plates.py` y versionarlos como
recursos de demo, o portar a `src/` un generador mínimo. Sirve para:
- darle a Figma Make datos realistas sin exponer ningún dato real;
- las pruebas end-to-end;
- **capturas y GIF del README**, y que un visitante del repo vea la app sin tener video propio.

### 4.5 Flujo con Figma Make

1. **Contrato y datos de muestra:** la spec de la API genera `openapi.json` y un paquete de JSON de ejemplo con sus
   recortes sintéticos (modo demo).
2. **Diseño en Figma Make:** se le describen las pantallas (§4.6) y se le dan los JSON de muestra. Qué acepta como
   entrada y cómo exporta el código está **NO VERIFICADO**. Hay que comprobarlo antes de empezar: si permite
   descargar el proyecto o enviarlo a GitHub, qué versión de React usa y qué librerías de componentes mete. También
   verificar la licencia o los términos de uso del código generado, para publicarlo bajo AGPL-3.0.
3. **Importación:** el código exportado entra en `frontend/` en una rama `feature/NNN-frontend-*`. Una spec lista qué
   se conserva (componentes, estilos) y qué se sustituye (datos de muestra por el cliente tipado).
4. **Cliente tipado:** tipos generados del OpenAPI (p. ej. `openapi-typescript`; versión a verificar en npm). Nada de
   `fetch` a mano repartido por los componentes.
5. **Revisión:** accesibilidad (contraste AA, todo usable con teclado, atajos C/E/R/B/S), sin dependencias de CDN, sin
   telemetría (revisar el `package.json` que genere Figma Make), `npm audit` limpio.

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
| **062** API de lectura | App factory, token, cabeceras, `videos`, `profiles`, `runs`, `sightings`, `crop`; tests con `TestClient` |
| **063** API de acciones | Procesar en un hilo + SSE + cancelación, decisiones, export, purga, métricas |
| **064** Comando `lector web` | Arranque en 127.0.0.1, puerto libre, abrir el navegador con el token, servir `dist/` |
| **065** Modo demo sintético | BD temporal y recortes sintéticos; genera los JSON de muestra para Figma Make |
| **066** Importar el frontend de Figma Make | `frontend/` compilable, cliente tipado, sin datos de muestra en producción |
| **067** Pantallas conectadas y pruebas E2E | Pruebas de componentes (Vitest) y E2E (Playwright) contra el modo demo |
| **068** Publicación | README (inicio rápido con `lector web`, capturas del modo demo), nivel F con `bind` loopback |

Herramientas nuevas que pide la web: **Node.js LTS** para compilar el frontend. Para que "clonar y ejecutar" siga
siendo simple, hay dos opciones (decisión pendiente, §6): exigir Node y `npm ci && npm run build` en el inicio rápido,
o publicar el `dist/` compilado en un Release, como los modelos.

---

## 5. Orden propuesto

| Paso | Qué | Bloquea a |
|---|---|---|
| 0 | Decidir la retención de recortes (§2.2) | 055 |
| 1 | **055** exportar dataset de legibilidad (antes del 2026-10-26) | 057 |
| 2 | Anotar un tramo con verdad (docs/07 Fase 1) + guía de captura | 3 |
| 3 | Calibrar perfiles (docs/07 Fase 2) y **060** parada temprana | — |
| 4 | **056** → **057** → **058** → **059**: filtro de legibilidad | web (galería "solo legibles") |
| 5 | ADR-016, SEG-28, **062**, **063**, **064**, **065** (backend y demo) | 066 |
| 6 | Verificar Figma Make (§4.5 paso 2), diseñar y **066**, **067** | 068 |
| 7 | **068** publicación y **061** tipo de vehículo | — |

Los pasos 4 y 5 pueden ir en paralelo: no comparten archivos.

---

## 6. Decisiones pendientes del usuario

1. **Retención de recortes:** ¿subir `crops_days` a 90 mientras se construye el filtro, o priorizar la spec 055 antes
   del 2026-10-26?
2. **GUI de escritorio:** ¿mantener PySide6 junto a la web, o retirarla cuando la web la iguale?
3. **Frontend compilado:** ¿exigir Node.js a quien clone, o publicar el `dist/` en un Release?
4. **Figma Make:** confirmar que tu plan permite exportar el código (§4.5).
5. **Filtro de legibilidad:** ¿mostrar las ocultas en una pestaña aparte (recomendado) o no mostrarlas nunca?

---

## 7. Criterios de "proyecto terminado"

- El inicio rápido del README lleva a la web en ≤ 6 comandos, probado desde un clon limpio (como el 2026-09-27).
- `lector web --demo` enseña la app completa con datos sintéticos; las capturas del README salen de ahí.
- En la vista por defecto, **≥ 60 % menos avistamientos inservibles** que hoy, con **≤ 5 % de legibles escondidas**
  (medido, §2.4).
- Velocidad ≥ 1× en 1080p con el perfil calibrado.
- M-01 a M-03 medidos con al menos un tramo anotado; el README publica las cifras, cumplan o no la meta.
- Suite completa (Python y frontend), `ruff`, `mypy --strict`, `npm run lint`/`tsc` y nivel F en verde.
