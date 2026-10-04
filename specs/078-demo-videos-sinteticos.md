# 078 - Modo demo con videos sintéticos reales y GIF del README

## Objetivo
Hoy los "videos" de `lector-web --demo` son archivos de texto (spec 069), así que "Ir al video" y "Captura completa"
(spec 076) muestran "no disponible". Esta spec hace que la demo genere **videos WebM sintéticos reales**, en los que
la placa de cada avistamiento cruza el encuadre en su intervalo de tiempo, y que cada corrida guarde el SHA-256 real de
su video. Así la función de saltar al segundo exacto funciona en la demo. Además añade un script que graba el recorrido
de la interfaz y lo convierte en `docs/img/demo.gif` para el README.

Todo es sintético (SEG-10): fondo gris, un rectángulo de vehículo y la placa dibujada por `render_plate`.

## Depende de
069, 071, 076, 077.

## Archivos a crear/modificar
- `src/lector_placas/web/demo.py`
- `tests/unit/web/test_demo.py`
- `frontend/e2e/demo.spec.ts` (la prueba 3 y, en la 4, el nombre del video) y `frontend/e2e/capturas.spec.ts` (nombre del video)
- `frontend/e2e/medios.spec.ts` (nuevo)
- `scripts/demo_gif.sh` (nuevo, ejecutable)
- `docs/img/demo.gif` y `docs/img/web-video.png` (los genera el script; no se dibujan a mano)

## Dependencias externas (verificadas el 2026-10-04 en este equipo)
- PyAV 18.1.0 incluye el códec `libvpx` (VP8). Con 640×360 a 10 fps, `deadline=realtime` y `cpu-used=8`, codifica
  620 frames en 0,8 s.
- El Chromium de Playwright no reproduce H.264 (códec propietario) y sí VP8/WebM; `.webm` ya está en
  `allowed_extensions` y en `VIDEO_MEDIA_TYPES` (`video/webm`).
- `ffmpeg` en `/usr/bin/ffmpeg`, para convertir a GIF.
- Playwright 1.63.0: `test.use({ video: { mode: "on", size } })` y `page.video().saveAs(ruta)` después de
  `page.close()`.

## Interfaces y comportamiento

### 1. `web/demo.py`
- `DEMO_VIDEOS` pasa a ser exactamente `("demo_parqueadero.webm", "demo_calle_1.webm", "demo_via_rapida.webm",
  "demo_patrulla.webm", "demo_calle_2.webm")`: el video de la corrida `n` es `DEMO_VIDEOS[n - 1]`.
- Constantes nuevas: `VIDEO_SIZE: Final[tuple[int, int]] = (640, 360)`, `VIDEO_FPS: Final[int] = 10`,
  `VIDEO_MS: Final[int] = 62_000`.
- `create_demo_root()` crea la carpeta temporal (0700) y `videos/` (0700) **vacía**; ya no escribe archivos.
- Se separa `_seed_sighting` en:
  - `_plan_sighting(rng, i, start)`, pura: devuelve un registro inmutable con `run_id`, `track_id`, `vehicle_type`,
    `texto`, `guardado`, `first`, `last`, `plate` (`ConsolidatedPlate`) y `quality`;
  - `_store_sighting(repository, crop_store, plan, start)`: guarda el recorte, el avistamiento y la revisión.
  Las llamadas a `rng` deben ocurrir **exactamente en el mismo orden que hoy** (ver el test de regresión).
- `seed_demo`, en este orden:
  1. `plans = [_plan_sighting(rng, i, start) for i in range(40)]` más los dos duplicados (copias de `plans[1]` y
     `plans[9]` con `track_id` 40 y 41, `first = 60_000`, `last = 61_000`, como en la spec 069).
  2. `shas = _write_demo_videos(config.under_root(Path("videos")), plans)`.
  3. `start_run` de cada corrida `n` con `video_sha256 = shas[n]` y `VideoInfo(640, 360, 0, VIDEO_MS, 10.0, "vp8")`.
  4. Guardar avistamientos, revisiones, `mark_duplicates` y `finish_run` como hoy; en `RunStats`, la duración del video
     pasa de `60_000 * n` a `VIDEO_MS`.
- `_write_demo_videos(videos_dir, plans) -> dict[int, str]`: para cada `n` de 1 a 5 escribe `videos_dir / DEMO_VIDEOS[n-1]`
  (modo 0600) con PyAV, contenedor WebM, stream `libvpx` a `VIDEO_FPS`, 640×360, `pix_fmt="yuv420p"`,
  `options={"deadline": "realtime", "cpu-used": "8"}`, `VIDEO_MS * VIDEO_FPS // 1000` frames. Devuelve
  `{n: sha256_file(ruta)}`. El frame `k` (instante `t = k * 100` ms) se dibuja así:
  1. Fondo BGR `(90, 90, 90)` y una línea de carril blanca discontinua: segmentos de 40 px cada 80 px en `y = 300`,
     grosor 4.
  2. Por cada plan de la corrida `n` con `first <= t <= last`:
     `x = int(40 + (t - first) / max(1, last - first) * 410)`, `y = 230`;
     rectángulo lleno `(x - 35, y - 70)`–`(x + 185, y + 60)` en BGR `(120, 60, 40)`;
     encima, `cv2.resize(render_plate(plan.guardado), (150, 50))` pegada en `[y:y+50, x:x+150]`.

### 2. `frontend/e2e/demo.spec.ts`, prueba 3
El título pasa a `ir al video`. Con una tarjeta seleccionada, pulsar `v`:
- el diálogo contiene un `video` visible;
- `expect.poll` sobre `video.readyState` llega a un valor `>= 1` en menos de 10 s;
- no aparece el texto `El video original no está disponible`.
Después, `Escape`; pulsar `f`: el `img` del diálogo tiene `naturalWidth > 0` (con `expect.poll`); `Escape`.

En la prueba 4 de `demo.spec.ts` y en `capturas.spec.ts`, `demo_entrada.mp4` pasa a `demo_parqueadero.webm`.

### 3. `frontend/e2e/medios.spec.ts`
- `test.skip(!process.env.LECTOR_MEDIOS, "solo con LECTOR_MEDIOS=1")`.
- `test.use({ viewport: { width: 1280, height: 720 }, colorScheme: "light", video: { mode: "on", size: { width: 1280, height: 720 } } })`.
- Una sola prueba `recorrido para el README`, con `await page.waitForTimeout(…)` entre pasos para que se vea:
  1. `/` → "Procesar" (navegación) → elegir `demo_parqueadero.webm` → pulsar el botón "Procesar" → esperar "Resultado"
     (pausa de 1200 ms).
  2. Pulsar "Lecturas" en la navegación (la corrida simulada de la demo no crea avistamientos) → esperar tarjetas (pausa de 1000 ms) → pulsar la primera → pausa de 800 ms → `c` →
     pausa de 1000 ms.
  3. `v` → esperar `readyState >= 2` → pausa de 3000 ms, con el video reproduciéndose → captura
     `page.screenshot({ path: "../docs/img/web-video.png", animations: "disabled" })` → `Escape` → pausa de 500 ms.
  4. `f` → esperar la imagen → pausa de 2000 ms → `Escape` → pausa de 800 ms.
  5. `await page.close()` y `await page.video()!.saveAs("../docs/img/demo.webm")`.

### 4. `scripts/demo_gif.sh`
`set -euo pipefail`. Desde la raíz del repo:
1. `cd frontend && npm run build && LECTOR_MEDIOS=1 npx playwright test e2e/medios.spec.ts && cd ..`.
2. `ffmpeg -y -i docs/img/demo.webm -vf "fps=12,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=5" docs/img/demo.gif`.
3. `rm docs/img/demo.webm` y escribe el tamaño con `ls -l docs/img/demo.gif`.

## Tests de aceptación (en prosa)
`tests/unit/web/test_demo.py`:
- `test_create_demo_root` (**cambia de expectativa**): la carpeta tiene modo 0700 y contiene `videos/` (0700) vacía.
- `test_demo_texts_unchanged` (nuevo, regresión del orden de `rng`): tras `seed_demo`, los cinco primeros avistamientos
  por `sighting_id` tienen `(sighting_id, ocr_text, first_seen_ms, last_seen_ms)` iguales a
  `(1, "DLT813", 0, 2961)`, `(2, "SVR309", 7000, 7830)`, `(3, "SYL364", 14000, 15924)`, `(4, "LCU844", 21000, 23373)`
  y `(5, "ZMM76C", 28000, 30133)` (valores medidos con la implementación de la spec 069 antes de este cambio).
- `test_demo_videos_are_real` (nuevo): tras `seed_demo` hay 5 archivos `.webm` en `videos/` con modo 0600;
  `run_video_hashes()` coincide con `sha256_file` de cada uno; `probe_duration_ms` da `62_000 ± 200`; y
  `PyAVFrameGrabber().grab(video de la corrida 1, 1480)` contiene al menos 500 píxeles cuyo valor BGR está a menos de
  40 de `PLATE_BGR` en cada canal.
- Los demás tests de la 069 no cambian (incluidos los conteos y `test_demo_survives_purge`).

## Definition of Done
- [ ] `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .` y `uv run mypy src` limpios.
- [ ] En `frontend/`: `npm run typecheck`, `npm test` y `npm run e2e` en verde (la prueba 3 nueva incluida).
- [ ] `bash scripts/demo_gif.sh` genera `docs/img/demo.gif` (pegar su tamaño; objetivo menos de 8 MB) y
      `docs/img/web-video.png`.
