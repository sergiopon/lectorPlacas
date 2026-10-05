# ADR-014 — Receta del primer fine-tuning real del OCR

- Estado: Aprobado (2026-09-27). Las tres decisiones de "Decisiones confirmadas" se aprobaron con un ajuste: la aceptación
  en dos niveles (aceptado / provisional / rechazado) y el test congelado.
- Requisitos: M-04 (CER ≤ 3 %), docs/04-evaluacion.md §5.3–5.4; ADR-003 (fine-tuning obligatorio).

## Contexto
Hechos verificados el 2026-09-27 sobre los datos locales (conteos agregados; ningún dato salió de la máquina):

| Hecho | Valor |
|---|---|
| `ocr_colombia` (salida de `chars-to-ocr`) | 806 recortes en `train` y 50 en `val` (856 en total), todos PNG |
| Imágenes del export de Roboflow (`raw/ocr_placas_colombia`, solo `train`) | 926 |
| Textos distintos | 490 en train, 39 en val; un mismo texto aparece hasta 18 veces (copias `.rf.<hash>` que el dHash no detecta) |
| Componentes independientes (mismo texto **o** misma imagen de origen) | 492: 441 carro, 24 con placa de moto, 27 con motocarro; los mayores tienen 18, 18 y 13 recortes |
| Patrones | `LLLDDD` 748, `LLLDDL` 60, `DDDLLL` 34, `LDDDDD` 8, `LLLDD` 2, `LDDDD` 2, `LLDDDD` 2 |
| Motos (`LLLDDL`/`LLLDD`) | 62 recortes (7,2 %); la meta de §5.3 es ≥ 20 % |
| Tamaño de los recortes | ancho 34–3 263 px (mediana ≈ 420), alto 19–2 259 px (mediana ≈ 280) |

Frente a las metas de §5.3 (≥ 5 000 recortes de train, ≥ 500 reales en val, ≥ 20 % motos, sintéticos ≤ 50 %) hay un
déficit de un orden de magnitud. Con 50 recortes de val (≈ 300 caracteres) un CER del 3 % son 9 errores: la
estimación de M-04 no distingue un 1 % de un 6 %. Además `chars_to_ocr` reservó a val un 10 % de los grupos de
origen y descartó los textos repetidos, lo que deja la val pequeña y sin motos suficientes.

Hechos verificados de la CLI `fast-plate-ocr train` 1.1.0 (`fast_plate_ocr/cli/train.py` instalado en `training/ocr/.venv`):
- Acepta un único `--annotations` y un único `--val-annotations`; `--weights-path` carga con `skip_mismatch=True`.
- **No tiene opción para congelar capas**: todas las capas del modelo construido quedan entrenables.
- Optimizador AdamW con `--lr` (0.001 por defecto), calentamiento lineal (`--warmup-fraction` 0.05), decaimiento
  coseno hasta `lr × --final-lr-factor` (0.01), EMA activada por defecto (`--use-ema`), `--label-smoothing` 0.01.
- `best.keras` se guarda con `save_best_only` según `--early-stopping-metric` (por defecto `val_plate_acc`, que sin
  cabeza de región se registra como `val_acc`); `EarlyStopping` usa `restore_best_weights=False`.
- Aumento de datos: `default_train_augmentation` de la librería, solo en train.
- `ocr_training/train.py` solo expone `--epochs`, `--batch-size`, `--patience` y `--seed`, y su test de revisión
  fija la lista exacta de argumentos: `--lr` y el resto quedan en los valores por defecto de la librería.

## Opciones evaluadas
1. **Entrenar con `ocr_colombia` tal cual** (806/50). Descartada: val sin poder estadístico y sin motos, y ningún
   conjunto separado para aceptar el modelo.
2. **Completar hasta 5 000 con sintéticos** (≈ 4 200 sintéticos, ≈ 84 %). Descartada: rompe el tope de sintéticos
   ≤ 50 %. El generador usa Liberation Sans y colores aproximados (tipografía oficial y RGB NO VERIFICADOS);
   con esa proporción el modelo aprendería el dominio sintético.
3. **Usar la misma partición para elegir el checkpoint y para aceptar el modelo.** Descartada: `best.keras` se elige
   por `val_acc` entre 150 épocas y medir M-04 en esa misma partición da una estimación optimista.
4. **Validación cruzada por k pliegues.** Descartada en esta iteración: la CLI admite una sola partición por corrida,
   costaría k entrenamientos en una GPU compartida y el modelo registrado seguiría siendo uno solo.
5. **Congelar el extractor de características.** Descartada: la CLI no lo soporta (verificado) y exigiría escribir un
   bucle de entrenamiento propio fuera de la librería.
6. **Rehacer la partición en `chars_to_ocr` (código de `src/`).** Descartada: cambia `src/` para
   algo que solo necesita el entrenamiento; la nueva partición se hace en `training/ocr` sin tocar el dataset base.
7. **Elegida: repartición por componente en train/val/test, sintéticos solo en train (≤ 50 %) con cuota de motos, y
   aceptación en un test real apartado frente al modelo base**.

## Decisión
**Datos (`mix_dataset`).** Los 856 recortes reales se agrupan en componentes (mismo texto de placa o misma
imagen de origen) y cada componente va entero a una partición. El reparto es estratificado por categoría (moto,
motocarro, otro) y determinista (SHA-256 del grupo con la semilla): **test 20 %, val 10 %, train 70 % de los
componentes**. Con `seed=0` (simulado sobre los datos actuales) quedan:

| Partición | Componentes | Recortes reales | Motos | Sintéticos |
|---|---|---|---|---|
| train | 345 | 553 | 36 | 553 (186 moto, 55 motocarro, 312 carro) |
| val | 49 | 88 | 2 | 0 |
| test | 98 | 215 (≈ 1 290 caracteres) | 24 | 0 |

- Sintéticos: tantos como reales de train (`--synthetic-ratio 1.0`, es decir 50 %), elegidos con cuota para que el train
  tenga **≥ 20 % motos**: 553 + 553 = **1 106 recortes de train, 20,1 % motos**. El 15 % de los sintéticos que no son de
  moto son motocarro y el resto carro. Se generan 1 500 con el generador de placas sintéticas (300 moto, 600 carro y 600
  motocarro, por el ciclo de estilos) para que haya margen; se descartan los que repiten un texto de val/test.
- **Val y test son 100 % reales.** Val solo elige el checkpoint; test solo se usa para aceptar.
- **Metas de §5.3 para esta iteración (declaradas como no cumplidas):** 1 106 de train frente a ≥ 5 000 y 88 + 215 reales
  de evaluación frente a ≥ 500. La meta de §5.3 se mantiene para las iteraciones siguientes.

**Hiperparámetros (CLI de entrenamiento).** `--epochs 150 --batch-size 64 --patience 40 --seed 0`; el resto, valores por
defecto de fast-plate-ocr (lr 0.001, calentamiento 5 %, coseno hasta 1e-5, EMA, label smoothing 0.01). Con 1 106 filas
son 18 pasos por época y 2 700 en total (135 de calentamiento). `patience 40` solo corta el tiempo: `best.keras` es el de
mejor `val_acc` en cualquier caso. El lote 64 es el valor con el que la librería fija su lr por defecto.

**Comandos** (desde `training/ocr`, con la GPU libre):
```bash
uv run python -m ocr_training.synthetic_plates --output syn_v1 --count 1500 --val-fraction 0 --seed 1
uv run python -m ocr_training.mix_dataset --real ocr_colombia --synthetic syn_v1 --output mix_v1 --seed 0
uv run python -m ocr_training.train --train mix_v1/train/annotations.csv --val mix_v1/val/annotations.csv \
    --epochs 150 --batch-size 64 --patience 40 --seed 0 --name colombia_v1
uv run python -m ocr_training.evaluate_ocr --crops mix_v1/test/annotations.csv \
    --candidate runs/colombia_v1/<fecha>/best.onnx
```

**Criterio de aceptación (`evaluate_ocr`)**, sobre `mix_v1/test` y con el mismo lector que usa el runtime
(`LicensePlateRecognizer` de fast-plate-ocr 1.1.0, BGR→RGB, textos inválidos vacíos). El modelo se acepta solo si se
cumplen todas las condiciones:
1. Hay al menos 100 recortes de test.
2. CER del candidato ≤ 3 % (M-04).
3. Cota superior del IC 95 % del CER ≤ 5 %. El IC se calcula por bootstrap de 2 000 réplicas **por componente**,
   porque los errores de un mismo vehículo están correlacionados.
4. El CER del candidato es menor que el del modelo base `fpo-cct-xs-v2-global` sobre el mismo test.
5. La coincidencia exacta del candidato no es menor que la del modelo base.

Si el CER de motos empeora respecto al modelo base, se emite un aviso pero no se rechaza el modelo: con ≈ 24 recortes
de 5 componentes la muestra no basta para decidir.

**Aceptación en dos niveles (ajuste aprobado el 2026-09-27).** `evaluate_ocr` no cambia: el operador toma el veredicto
leyendo las cinco condiciones de su reporte. Negarse a sustituir un modelo peor por otro claramente mejor no protege
nada: la protección contra falsos positivos la da el consolidador (M-01), no el OCR.

| Resultado | Condiciones | Qué pasa |
|---|---|---|
| **Aceptado** | Cumple 1 a 5 | Se registra; cumple M-04. |
| **Provisional** | Cumple 1, 4 y 5, pero falla la 2 o la 3 | Se registra y sustituye al modelo base, marcado como **que no cumple M-04**. |
| **Rechazado** | Falla la 1, la 4 o la 5 | No se registra. |

- Un modelo **provisional** cuyo CER de motos empeora respecto al modelo base **no** sustituye al base (queda sin
  registrar, como un rechazado). En un modelo aceptado esa regresión solo emite el aviso descrito arriba.
- Para un provisional, el reporte JSON y el campo `source` de la entrada del manifiesto dicen explícitamente
  "provisional: no cumple M-04" y citan qué condición falló (2 o 3) con sus cifras.
- Con `decision=RECHAZAR` en el reporte de `evaluate_ocr`, el operador **no** borra ni descarta el modelo antes de
  aplicar esta tabla: el reporte no distingue entre provisional y rechazado.

**Registro.** Con un modelo aceptado o provisional, el operador:
1. Copia el `sha256` y el `size_bytes` que imprime `train.py` en la entrada `fpo-cct-xs-v2-colombia` de
   `config/models.yaml` (con el `source` que corresponda al nivel).
2. Cambia `models.ocr.model_id` en `config/lector.yaml`.
3. Ejecuta `lector models verify` y `lector evaluate-ocr --crops training/ocr/datasets/mix_v1/test/annotations.csv`,
   que debe dar el mismo CER que `evaluate_ocr` con una diferencia de 0,005 como máximo. Si no, hay un desajuste de
   preprocesado y se investiga antes de usar el modelo.

**No se registra** un modelo rechazado, ni un provisional con regresión en motos. Tampoco si el modelo se eligió
mirando el test: cambiar la receta después de ver el test obliga a crear otra mezcla con otra `seed` y a declararlo.
Sin registro, `models.ocr.model_id` sigue en `fpo-cct-xs-v2-global` y el `.onnx` copiado a
`models/fpo-cct-xs-v2-colombia/` queda sin registrar. El runtime no lo carga porque su SHA-256 no coincide con el
manifiesto (ADR-012).

**Test congelado.** El `test` de `mix_v1` (`--seed 0`) es la referencia fija de todas las versiones futuras del OCR:
no se vuelve a repartir y nunca se usa para entrenar ni para elegir checkpoint. Los datos nuevos (p. ej. lecturas
revisadas con `export-reviewed`) entran solo a `train` o `val` y no mueven los vehículos ya asignados a `test`.

**Esta es la versión 1.** Se registra con su tamaño real (1 106 de train, 215 de test); no se presenta como
cumplimiento de las cantidades de §5.3, que siguen siendo el objetivo de la versión 2.

## Consecuencias
- (+) Ningún vehículo aparece a la vez en train y en val/test. La aceptación se mide con datos reales no vistos, con
  intervalo y contra el modelo base.
- (+) La cuota de motos se cumple en train sin superar el 50 % de sintéticos.
- (−) El test de ≈ 215 recortes (≈ 98 vehículos) sigue siendo pequeño: el IC 95 % puede superar el 5 % aunque el CER
  puntual sea bueno; en ese caso el modelo queda como provisional (no cumple M-04) si mejora al base, no se rechaza.
- (−) Se entrena con 303 recortes reales menos que con `ocr_colombia` completo (553 frente a 856), que se reservan para val y test.
- (−) Las motos de train son en su mayoría sintéticas (186 de 222); si su render no se parece a las reales, el aviso
  de regresión en motos lo mostrará.

## Siguientes iteraciones (candidatas, sin decidir)
- **Datos propios revisados**: `mix_dataset --real ocr_colombia --real own/reviewed-<fecha>` los añade con la
  misma regla de componentes. Es la vía verificable para acercarse a ≥ 500 reales en evaluación.
- **Recortes de `usco`** (`training/detector/datasets/raw/usco`, 3 751 archivos en el export con aumentos; 1 106
  imágenes según Roboflow): ya son recortes de placa, pero **no tienen texto** y habría que etiquetarlo a mano.
  Licencia MIT declarada y origen colombiano NO VERIFICADOS.
- **`motos_placas`**: sus clases `H`, `I`, `Q` podrían ser caracteres. NO VERIFICADO; no sirve para el OCR sin texto
  completo.
- **Ajustar el lr** (`--lr`, soportado por la CLI) si el log muestra sobreajuste: `acc` de train muy por encima de
  `val_acc`. Requiere modificar `train.py` y su test de lista exacta. El valor adecuado para fine-tuning
  está NO VERIFICADO.

## Decisiones confirmadas (2026-09-27)
1. **Cantidades de §5.3.** La primera iteración no las cumple (1 106 de train y 303 reales de evaluación) y se registra
   igualmente si pasa el criterio. Las metas de §5.3 no se rebajan: son el objetivo de la versión 2, cuya fuente
   verificable son las lecturas revisadas. Un tope de sintéticos ≤ 50 % hace inalcanzable 5 000 con los
   datos actuales sin que el modelo aprenda el render.
2. **30 % de los componentes reales para val y test.** Con menos, el test bajaría de 100 vehículos y el IC dejaría de
   medir; la validación cruzada multiplica el costo por 5 y no deja un test fijo comparable entre versiones. Se añade
   la condición del test congelado.
3. **Umbrales nuevos:** IC 95 % ≤ 5 %, mínimo de 100 recortes de test y mejora estricta sobre el modelo base, con el
   nivel provisional descrito arriba.
