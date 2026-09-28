# lectorPlacas

Lector local de placas colombianas (ALPR) a partir de video. Detecta los vehículos, los sigue entre frames, lee su
placa varias veces y vota el resultado. Lo que el sistema no puede asegurar lo deja para que una persona lo revise. Todo
corre en tu equipo: **no se conecta a internet mientras procesa**, y la base de datos y los recortes de placa se
guardan cifrados.

Licencia: AGPL-3.0 (ver `LICENSE` y `docs/adr/ADR-008-licencia-agpl.md`).

---

## Índice
1. [Qué hace, en una imagen](#1-qué-hace-en-una-imagen)
2. [Requisitos](#2-requisitos)
3. [Instalación y primer uso](#3-instalación-y-primer-uso)
4. [Uso diario con la aplicación de escritorio](#4-uso-diario-con-la-aplicación-de-escritorio)
5. [Uso desde la terminal (CLI)](#5-uso-desde-la-terminal-cli)
6. [Cómo decide el sistema](#6-cómo-decide-el-sistema)
7. [Configuración](#7-configuración)
8. [Dónde queda cada cosa](#8-dónde-queda-cada-cosa)
9. [Medir la calidad](#9-medir-la-calidad)
10. [Entrenar los modelos](#10-entrenar-los-modelos)
11. [Seguridad y privacidad](#11-seguridad-y-privacidad)
12. [Desarrollo](#12-desarrollo)
13. [Problemas frecuentes](#13-problemas-frecuentes)
14. [Estado actual y próximos pasos](#14-estado-actual-y-próximos-pasos)

---

## 1. Qué hace, en una imagen

```
video ──► decodificar (PyAV) ──► muestrear frames según el perfil
      ──► detectar vehículos (YOLO26n)  ──► seguirlos (BoT-SORT)
      ──► detectar la placa DENTRO del recorte del vehículo
      ──► leer la placa (fast-plate-ocr)   × varias veces por vehículo
      ──► al salir el vehículo de cámara: votar las lecturas y validar el formato colombiano
      ──► guardar el avistamiento (SQLCipher) + el mejor recorte cifrado (AES-GCM)
      ──► confirmado  ó  "por revisar" con sus motivos
```

Cada vehículo que pasa produce un **avistamiento**, que queda en uno de estos estados:

| Estado | Quién lo pone | Significado |
|---|---|---|
| Confirmada | el sistema o el revisor | La lectura es correcta |
| Por revisar | el sistema | Hay dudas; se muestran los motivos |
| Corregida | el revisor | El texto estaba mal y se corrigió |
| Descartada | el revisor | No es una placa (detección falsa, fragmento) |
| Borrosa | el revisor | Es una placa, pero ni una persona puede leerla |

La filosofía es **precisión primero**: el sistema prefiere dejar algo por revisar antes que confirmar una placa
equivocada.

---

## 2. Requisitos

- **Linux** (probado en Fedora 44).
- **GPU NVIDIA con CUDA 13** (probado con una RTX 5050). Sin GPU funciona en CPU, mucho más lento
  (`inference.execution_provider: cpu` en `config/lector.yaml`).
- **[uv](https://docs.astral.sh/uv/)** en `~/.local/bin/uv`. uv instala Python 3.13 y todas las dependencias; no
  hace falta instalar Python a mano.
- Un **llavero del sistema** (GNOME Keyring o KWallet) para guardar la clave maestra.
- Opcional: `strace`, para los chequeos no funcionales (`scripts/nivel_f.py`).

> ⚠️ **Hay otro programa llamado `lector`** (un lector de ebooks en `/usr/bin/lector`). Ejecuta siempre este
> proyecto con `uv run lector ...` desde la carpeta del repo, o activa el entorno (`source .venv/bin/activate`).

---

## 3. Instalación y primer uso

```bash
cd ~/Documents/projects/lectorPlacas
export PATH=~/.local/bin:$PATH        # conviene añadirlo a ~/.bashrc

uv sync --locked                      # crea .venv con Python 3.13 y todo lo necesario
uv run python scripts/verify_gpu.py   # opcional: comprueba que ONNX Runtime ve la GPU

uv run lector key init                # crea la clave maestra en el llavero (una sola vez)
uv run lector models fetch            # descarga los modelos públicos (única orden con red)
uv run lector models verify           # comprueba el hash SHA-256 de todos los modelos
```

Los modelos entrenados en este proyecto (`yolo26n-coco`, `yolo26n-plates`, `fpo-cct-xs-v2-colombia`) no se
descargan: se generan con las herramientas de `training/` y ya están en `models/`.

Pon tus videos en **`videos/`**. Por seguridad solo se aceptan videos dentro de esa carpeta, con extensión `.mp4`,
`.mov`, `.mkv`, `.avi`, `.m4v` o `.webm` y hasta 4 GB.

---

## 4. Uso diario con la aplicación de escritorio

```bash
uv run lector-gui
```

La ventana tiene dos secciones, arriba:

**Procesar**
1. Elige un video de `videos/`.
2. Elige el escenario (perfil): *Parqueadero o entrada*, *Calle con tráfico lento* o *Vía rápida* (ver §7).
3. Pulsa procesar. Se ve el avance y se puede cancelar. Al terminar, el botón *Revisar N placas pendientes* (o *Ver
   lecturas*) lleva directo a sus lecturas.

**Lecturas**: una galería con una tarjeta por placa (recorte + texto).
- Filtros arriba: *Por revisar*, *Confirmadas*, *Corregidas*, *Descartadas*, *Borrosas*, *Todas*. También se
  puede buscar por placa y filtrar por video.
- Al hacer clic en una tarjeta, el panel derecho la muestra en grande, junto con lo que leyó el sistema, su seguridad
  y **por qué hay que revisarla**.
- Decisiones, con botón o con teclado:

| Tecla | Acción |
|---|---|
| `C` | Es correcta |
| `E` | Corregir el texto (`Enter` guarda, `Esc` cancela) |
| `R` | No es una placa |
| `B` | Placa borrosa: es una placa, pero no se lee |
| `S` | Saltar |

Tras decidir, pasa sola a la siguiente pendiente.

**Botón *Más*** (barra superior):
- *Exportar, retención y métricas*: exporta a CSV, purga los datos vencidos y muestra las métricas de la revisión.
- *Historial de videos*: las corridas anteriores, con sus conteos.

---

## 5. Uso desde la terminal (CLI)

Todo lo que hace la GUI se puede hacer por terminal. Siempre con `uv run lector ...`.

| Orden | Para qué |
|---|---|
| `lector key init` | Crear la clave maestra (primera vez) |
| `lector models fetch` / `verify` | Descargar / verificar modelos |
| `lector process videos/<v>.mp4 [--profile calle_lenta]` | Procesar un video |
| `lector review [--limit N] [--status unverified\|confirmed]` | Revisar en una ventana OpenCV. Teclas: `C` confirmar, `E` editar, `R` rechazar, `B` borrosa, `S` saltar, `Q` salir. Con `--status confirmed` se **auditan** las confirmadas automáticas |
| `lector export [--status ...]` | Exportar avistamientos a CSV (`data/exports/`) |
| `lector purge` | Borrar lo que venció según la retención (también corre sola al iniciar cada orden) |
| `lector evaluate --video <v> --ground-truth <gt.json> [--profile p]` | Medir precisión y recall contra una anotación manual (§9) |
| `lector evaluate-review` | Métricas a partir de tus revisiones: precisión de confirmadas, CER real, etc. |
| `lector evaluate-ocr --crops <csv>` | CER del OCR sobre recortes anotados |
| `lector evaluate-detector [--dataset d] [--split val]` | Precisión/recall del detector de placas |
| `lector dataset download` / `prepare` | Descargar y preparar datasets de Roboflow (requiere `ROBOFLOW_API_KEY`) |
| `lector dataset merge-detection` / `chars-to-ocr` | Pasos intermedios de `prepare` |
| `lector dataset export-reviewed` | Exportar tus recortes revisados para reentrenar el OCR |

Opción global: `lector --config config/<otro>.yaml ...`. La config alternativa **debe estar dentro de `config/`**.

---

## 6. Cómo decide el sistema

Por cada vehículo se guardan hasta `max_readings_per_track` lecturas (8 en *calle lenta*): **las de mejor calidad**,
es decir, la placa más ancha en pantalla y, con el mismo ancho, la más nítida. Al salir el vehículo de cámara se
consolidan (algoritmo en `docs/adr/ADR-007-votacion.md`):

1. Se vota carácter por carácter, ponderando por la confianza del OCR.
2. Se prueban los formatos colombianos del catálogo (`config/lector.yaml`), p. ej. `ABC123` (carro), `ABC12D` (moto
   nueva), `ABC12` (moto antigua) y `123ABC` (motocarro). Se corrigen confusiones típicas (0↔O, 1↔I, 8↔B, 5↔S).
3. Si esa corrección cambiaría una lectura que ya era una placa válida por otra, gana la lectura original y queda
   **por revisar** ("Podría ser otra placa").
4. Se confirma solo si no hay ningún motivo de duda.

Motivos de "por revisar":

| Motivo (GUI) | Código |
|---|---|
| Se leyó pocas veces | `insufficient_readings` |
| El lector no estaba seguro | `low_confidence` |
| Las lecturas no coinciden entre sí | `low_agreement` |
| No parece una placa colombiana | `unrecognized_format` |
| Formato de placa poco común | `unverified_format` |
| El formato no corresponde al tipo de vehículo | `vehicle_format_mismatch` |
| Encaja en más de un formato | `ambiguous_format` |
| Podría ser otra placa: una letra o un número dudoso | `correction_conflict` |

En la base de datos, `ocr_text` es lo que leyó el sistema (no cambia nunca) y `plate_text` es el texto vigente (la
revisión lo sobrescribe).

---

## 7. Configuración

Archivo principal: **`config/lector.yaml`** (esquema en `docs/03-modelo-datos.md`).

- `models`: qué detector de vehículos, detector de placas y OCR se usan. El OCR en uso es `fpo-cct-xs-v2-colombia`.
  Para probar el detector de placas propio:
  `plate_detector: {backend: yolo, model_id: yolo26n-plates, input_size: 640}`.
- `profiles`: un perfil por escenario:

| Parámetro | parqueadero | calle_lenta | calle_rapida |
|---|---|---|---|
| `target_fps` (frames analizados por segundo) | 10 | 15 | 30 |
| `max_readings_per_track` (lecturas que se votan) | 8 | 8 | 6 |
| `track_finalize_after_ms` (cuándo se da por ido un vehículo) | 3000 | 2000 | 1000 |
| `min_readings` / `confirm_threshold` / `min_agreement` | 3 / 0.90 / 0.60 | 3 / 0.90 / 0.60 | 2 / 0.90 / 0.60 |
| `min_plate_width_px` (ancho mínimo para intentar leer) | 20 | 20 | 20 |
| `min_sharpness` (0 = sin filtro) | 0.0 | 0.0 | 0.0 |

  Estos valores son **provisionales**: se calibran en la Fase 2 de `docs/07-plan-mejora-lectura.md`.
- `plate_formats`: catálogo de formatos con su fuente normativa. Los que tienen `verified: false` nunca se confirman
  solos.
- `retention`: recortes 30 días, registros 90 días y exportaciones de entrenamiento 180 días.

**`config/models.yaml`** es el manifiesto de modelos: archivo, URL y hash SHA-256. Si un `.onnx` no coincide con su
hash, no se carga.

---

## 8. Dónde queda cada cosa

```
config/            lector.yaml (configuración), models.yaml (manifiesto de modelos), datasets.yaml (Roboflow)
videos/            tus videos de entrada (única carpeta permitida)
data/lector.db     base de datos cifrada (SQLCipher)             ← haz copia antes de actualizar versiones
data/crops/        recortes de placa cifrados (AES-GCM)
data/exports/      CSV exportados
data/eval/         anotaciones (ground_truth/) y reportes de evaluación (reports/)
logs/lector.log    registro, sin textos de placa en claro
models/            modelos ONNX verificados por hash
training/detector  entrenamiento del detector de placas (proyecto uv aparte)
training/ocr       entrenamiento del OCR colombiano (proyecto uv aparte)
src/lector_placas  código (ver §12)
docs/              requisitos, contratos, modelo de datos, evaluación, ADRs y plan de mejora
specs/             especificaciones numeradas (000–054) y su estado en specs/README.md
```

La clave maestra **no** está en disco: vive en el llavero del sistema. Sin ella no se pueden leer ni la base ni los
recortes.

---

## 9. Medir la calidad

Criterios completos en `docs/04-evaluacion.md`. Métricas principales:

| Métrica | Qué mide | Meta |
|---|---|---|
| M-01 | Precisión de las confirmadas | ≥ 98 % |
| M-02 | Recall total (placas legibles encontradas) | ≥ 90 % |
| M-03 | Recall de confirmadas | ≥ 75 % |
| M-04 | CER del OCR (errores por carácter) | ≤ 3 % |
| M-05 | Velocidad (duración del video / tiempo de proceso) | ≥ 1,0 |

**Sin anotar nada** (a partir de tus revisiones):
```bash
uv run lector review --status confirmed   # audita confirmadas automáticas
uv run lector evaluate-review              # precisión estimada, CER real, desglose de motivos
```

**Con anotación manual** (lo más fiable): crea `data/eval/ground_truth/<sha256 del video>.json` siguiendo el formato
de `docs/04-evaluacion.md` §2 (placas, tipo de vehículo, tiempos) y ejecuta:
```bash
uv run lector evaluate --video videos/<v>.mp4 --ground-truth data/eval/ground_truth/<sha>.json --profile calle_lenta
```
Nota: `evaluate` procesa el video de verdad, así que sus avistamientos aparecen también en la galería.

---

## 10. Entrenar los modelos

Cada carpeta de `training/` es un proyecto uv independiente, con su propio lock y torch/CUDA. Se ejecuta **desde su
carpeta**. Los datos (`datasets/`) y los resultados (`runs/`) no se versionan.

**Datasets de Roboflow** (desde la raíz):
```bash
export ROBOFLOW_API_KEY=...
uv run lector dataset prepare     # descarga, fusiona para el detector y genera recortes para el OCR
```

**Detector de placas** (desde `training/detector`):
```bash
uv run python -m detector_training.fetch_base_weights
uv run python -m detector_training.train_plates --data merged/data.yaml --name <run>
```
Publica en `models/yolo26n-plates/` e imprime el hash, que se copia a `config/models.yaml`.

**OCR colombiano** (desde `training/ocr`), receta de ADR-014:
```bash
uv run python -m ocr_training.fetch_assets
uv run python -m ocr_training.synthetic_plates --output syn_v1 --count 1500 --val-fraction 0 --seed 1
uv run python -m ocr_training.mix_dataset --real ocr_colombia --synthetic syn_v1 --output mix_v1 --seed 0
uv run python -m ocr_training.train --train mix_v1/train/annotations.csv --val mix_v1/val/annotations.csv \
    --epochs 150 --batch-size 64 --patience 40 --seed 0 --name colombia_v1
uv run python -m ocr_training.evaluate_ocr --crops mix_v1/test/annotations.csv --candidate runs/colombia_v1/<fecha>/best.onnx
```
- El `test` de `mix_v1` está **congelado**: nunca entrena y sirve para comparar todas las versiones.
- `train.py` **sobrescribe** `models/fpo-cct-xs-v2-colombia/` aunque el modelo salga peor. Guarda antes una copia del
  `.onnx` en uso.

**Reentrenar con tus revisiones** (spec 054; disponible cuando esté integrada):
```bash
uv run lector dataset export-reviewed                        # desde la raíz → training/ocr/datasets/own/reviewed-<fecha>
cd training/ocr
uv run python -m ocr_training.mix_dataset --frozen-from mix_v1 --real own/reviewed-<fecha> \
    --synthetic syn_v1 --output mix_v2 --seed 0
uv run python -m ocr_training.train --train mix_v2/train/annotations.csv --val mix_v2/val/annotations.csv \
    --epochs 150 --batch-size 64 --patience 40 --seed 0 --name colombia_v2
uv run python -m ocr_training.evaluate_ocr --crops mix_v2/test/annotations.csv --candidate runs/colombia_v2/<fecha>/best.onnx
uv run python -m ocr_training.evaluate_ocr --crops mix_v2/test_video/annotations.csv \
    --candidate runs/colombia_v2/<fecha>/best.onnx --baseline runs/colombia_v1/<fecha>/best.onnx
```
Con menos de 100 recortes en `test_video`, la decisión dirá RECHAZAR por muestra insuficiente. Es lo esperado: allí
se compara el CER de v2 con el de v1.

---

## 11. Seguridad y privacidad

Reglas completas en `reglas-seguridad.md` (SEG-01..SEG-27). Lo esencial:
- **Sin red en ejecución.** Todas las órdenes bloquean la red, salvo `models fetch`, `dataset download` y
  `dataset prepare`.
- **Cifrado en reposo.** La base va en SQLCipher y los recortes en AES-GCM, con subclaves derivadas de la clave maestra
  del llavero.
- **Sin placas en claro** en logs, reportes, auditoría ni mensajes de error.
- **Retención.** Los datos vencidos se purgan solos al iniciar cada orden.
- **Modelos verificados** por SHA-256 en cada carga. Solo ONNX, nunca pickles de PyTorch.
- **Entradas acotadas.** Solo videos de `videos/`, con extensión y tamaño permitidos. Las rutas se resuelven dentro
  del proyecto.

---

## 12. Desarrollo

Arquitectura limpia (`ARQUITECTURA.md`). Regla de dependencia verificada por `tests/architecture`:

```
domain  ←  application  ←  infrastructure / adapters  ←  evaluation / datasets  ←  cli  (composition root)
                                                                                  ←  gui  (2.º composition root, PySide6)
```

| Capa | Contenido |
|---|---|
| `domain` | Entidades, catálogo de formatos, corrección posicional, consolidación (solo stdlib) |
| `application` | Casos de uso (`ProcessVideo`, `ReviewSightings`, `DecideSighting`, exportar, purgar) y puertos (Protocols) |
| `adapters` | ONNX (detectores, OCR), BoT-SORT, PyAV, SQLCipher, recortes cifrados, ventana OpenCV |
| `infrastructure` | Configuración, claves, registro de modelos, red controlada |
| `evaluation` / `datasets` | Métricas y herramientas de datasets |
| `cli` / `gui` | Puntos de entrada |

Comandos:
```bash
uv run pytest                                  # toda la suite (marcadores: -m gpu, -m integration)
QT_QPA_PLATFORM=offscreen uv run pytest tests/unit/gui
uv run ruff check . && uv run ruff format --check .
uv run mypy src                                # modo strict
uv run pre-commit run --all-files
uv run python scripts/nivel_f.py               # red (strace), permisos, cifrado, placas en claro, velocidad, VRAM
```

Cómo se trabaja: **spec-driven development**. Cada cambio se describe primero en una spec de `specs/` y se implementa en
una rama `feature/NNN-*` con merge `--no-ff`. El estado de cada spec y el registro de correcciones están en
`specs/README.md`. Las firmas exactas están en `docs/02-contratos.md` y las decisiones, en `docs/adr/`.

---

## 13. Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| `ModuleNotFoundError: No module named 'imghdr'` al ejecutar `lector` | Se ejecutó el lector de ebooks del sistema. Usa `uv run lector` |
| "manifiesto de modelos inválido" con `--config` | La config alternativa debe estar dentro de `config/` |
| Va muy lento / "cae a CPU" | Revisa `scripts/verify_gpu.py` y que `inference.execution_provider` sea `cuda` |
| Error de clave o del llavero | Ejecuta `lector key init` en una sesión de escritorio con llavero desbloqueado. Sin la clave original, los datos cifrados no se recuperan |
| Un modelo "no verificado" tras entrenar | `train.py` sobrescribió el `.onnx`. Restaura tu copia o registra el hash nuevo en `config/models.yaml` |
| La GUI avisa de Wayland | Es solo un aviso; para forzarlo: `QT_QPA_PLATFORM=wayland uv run lector-gui` |
| "versión de esquema no soportada" | La base es de una versión más nueva que el código. Actualiza el repo; no la borres |

---

## 14. Estado actual y próximos pasos

- Specs 000–053 implementadas; la 054 (reentrenar con reparto congelado) está en curso. Detalle en `specs/README.md`.
- OCR en uso: `colombia_v1`, nivel **provisional** (CER 3,7 % en el test congelado). En video real, el CER medido con
  tus revisiones es 16 %.
- Plan de mejora en **`docs/07-plan-mejora-lectura.md`**:
  - Fases 0 y 0b–0c (hechas): auditoría, conflicto de corrección (050), mejores lecturas por track (051) y "placa
    borrosa" (052–053).
  - Fase 1: anotar la verdad de 1 o 2 videos.
  - Fase 2: calibrar los perfiles.
  - Fase 4: reentrenar el OCR con más recortes revisados.
