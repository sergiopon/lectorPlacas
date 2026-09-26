# 06 — Plan de pruebas

Las pruebas se organizan en niveles. Cada nivel tiene un responsable y un momento de ejecución. Ninguna prueba que
corra un agente usa datos reales.

## 1. Niveles

| Nivel | Qué verifica | Autor | Cuándo se ejecuta | Marcador / comando |
|---|---|---|---|---|
| A. Estático | Estilo, tipos estrictos, regla de dependencia, greps de seguridad | Spec 000 + Opus | Cada entrega | `ruff`, `mypy src`, `tests/architecture` |
| B. Aceptación | El comportamiento exacto de cada spec | Opus (dentro de la spec) | Cada entrega | `pytest tests/unit` |
| C. Revisión (ocultos) | Casos borde que la spec no enumera; detectan implementaciones hechas "a la medida" de los tests | Opus, **después** de la entrega y sin mostrarlos al implementador | Al revisar la spec; luego como regresión | `pytest tests/review` |
| D. Integración | Librerías nativas reales: PyAV, SQLCipher, ONNX Runtime en CPU, archivos cifrados, permisos | Spec | Cada entrega | `pytest -m integration` |
| E. GPU / extremo a extremo | CUDA sm_120, sesiones ORT CUDA, pipeline completo con modelos reales sobre video sintético | Spec | Olas 0, 3, 4 y 6, en la RTX 5050 | `pytest -m gpu` |
| F. No funcionales | Velocidad, VRAM, red bloqueada, permisos de archivos, placas en logs | Opus | Tras la ola 6 | Ver §3 |
| G. Calidad real | Métricas M-01..M-06 con videos y ground truth reales | Usuario, local | Fase 5 | `lector evaluate` |

**Regla de regresión:** una spec solo se aprueba si toda la suite `pytest -m "not gpu"` sigue en verde, además de
`-m gpu` cuando aplique.

## 2. Tests de revisión (nivel C) planificados

Viven en `tests/review/test_review_NNN.py`. Opus los escribe al revisar la spec NNN. Si fallan, la entrega vuelve al
implementador con la descripción del caso, sin el código del test.

| Spec | Casos |
|---|---|
| 001 | `BoundingBox.expand(0)` devuelve la misma caja; `clip` con una caja exactamente en el borde; `Sighting.created_at` con microsegundos |
| 004 | Tres longitudes con la misma masa de confianza; todas las lecturas sin patrón de su longitud; empate de caracteres resuelto por orden ASCII; mapa de confusiones vacío; lecturas con confianza 0; `format_ids` compatibles filtrados por tipo de vehículo |
| 006 | Perfil con claves extra; `confusions` con una letra minúscula; ruta con `..` en `allowed_dirs` |
| 008 | 1 000 cifrados sin repetir nonce; `decrypt` con un blob exactamente de 28 bytes |
| 010 | Video con un solo frame; `close()` antes de consumir `frames()` |
| 012 | Cajas totalmente fuera del lienzo; scores `NaN` |
| 016 | Detecciones cuya confianza es menor que `track_activation_threshold` no crean track |
| 019 | Manifiesto con `model_id` repetido; descarga cortada a la mitad (se borra el `.part`) |
| 020 | Rollback: un error dentro de `save_sighting` no deja la placa enlazada; `ON DELETE CASCADE` al borrar corridas; paginación con `offset` más allá del final |
| 021 | Un `.tmp` huérfano se borra con `delete_older_than`; ref con mayúsculas es rechazada |
| 022 | Placa pasada como argumento `%s` y como parte de `extra`; varias placas en un mensaje |
| 023 | Un track observado sin lecturas y reabierto tras `pop_inactive` |
| 024 | Varios tracks con `max_ocr_per_frame=1` (solo el de mayor área se lee); error en `consolidate` marca la corrida como fallida; la placa detectada fuera del frame tras trasladarla es descartada |
| 025 | Purga idempotente (segunda ejecución da todo 0) |
| 028 | `process` con la red realmente bloqueada: un intento de socket en un adaptador termina con código 7 |
| 029 | Un registro `rejected` con texto correcto no cuenta; tolerancia exacta en el borde (±1000 ms) |
| 031 | Dataset sin carpeta `test/`; etiqueta con clase fuera de `names` |

## 3. Pruebas no funcionales (nivel F)

| Prueba | Método | Criterio |
|---|---|---|
| Red bloqueada | `pytest` de extremo a extremo con `block_network()` real y un modelo sintético; más `strace -f -e trace=connect` durante `lector process` en la RTX 5050 | 0 llamadas `connect` a la red |
| Permisos | Script que recorre `data/` y `logs/` tras una corrida | Directorios 0700, archivos 0600 |
| Placas en claro | Buscar el patrón de `PLATE_PATTERN` en `logs/`, exportaciones del `audit_log` y reportes tras una corrida con placas sintéticas renderizadas | 0 coincidencias sin enmascarar |
| Cifrado en reposo | Buscar `SQLite format 3`, `\x89PNG` y los textos sintéticos en `data/` | 0 coincidencias |
| Velocidad (alerta temprana) | Video sintético 1080p30 de 60 s generado con PyAV, modelos reales, perfil `calle_rapida` | `speed_factor >= 1.0`; la cifra definitiva (M-05) sale del nivel G |
| VRAM (alerta temprana) | La misma corrida con `VramMonitor` | pico ≤ 4096 MiB |

## 4. Datos de prueba

- **Imágenes:** numpy u OpenCV generadas en el test (ruido con semilla, figuras, texto con `cv2.putText`).
- **Videos:** PyAV (`tests/fixtures/synthetic_video.py`), códec `mpeg4`, con o sin rotación.
- **Modelos:** ONNX sintéticos de salida constante (`tests/fixtures/synthetic_onnx.py`). Los modelos reales solo se
  usan en tests marcados `gpu`/`integration` que se omiten si no están descargados.
- **Placas:** textos inventados que cumplen el catálogo (`ABC123`, `XYZ98K`, `123ABC`, `R12345`).
- **Claves:** `FakeKeyProvider` con 32 bytes deterministas. El keyring real nunca se usa en tests.

## 5. Informe por entrega (lo produce Haiku)

```
spec=NNN agente=<...> ronda=<n>
archivos_fuera_de_lista=<ninguno | lista>
tests_aceptacion_intactos=<sí | no: lista>
pytest_no_gpu=<pasados/total> fallos=<primeros 3 nombres + 5 líneas de error>
pytest_gpu=<n/a | pasados/total>
ruff=<ok | n errores> ruff_format=<ok | n archivos> mypy=<ok | n errores (primeros 5)>
greps_seguridad=<ok | hallazgos>
```
