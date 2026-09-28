# 050 - Dominio: la corrección posicional no reemplaza una lectura que ya era una placa válida

## Objetivo
Impedir que el consolidador confirme un texto que solo encaja en un formato porque la corrección posicional (0↔O, 1↔I,
8↔B, 5↔S) cambió lo que el OCR leyó. Así se produjeron las dos confirmadas erróneas de la auditoría del 2026-09-27
(docs/07 §1.1). En ambas, un track clasificado como moto con lecturas unánimes del tipo `KLM128` (placa válida de carro)
se "corrigió" a `KLM12B` para encajar en `co_moto` y se confirmó con confianza 0,99, porque la confianza del carácter
corregido es la que el OCR dio al dígito.

Regla nueva: si el voto **sin corrección** ya produce un texto que acepta algún formato del catálogo, y la selección por
patrones eligió un texto distinto, el resultado es el texto sin corregir y queda `unverified` con la razón nueva
`CORRECTION_CONFLICT`. La corrección sigue aplicándose cuando el voto sin corregir no es una placa válida (p. ej.
`0BC123` → `OBC123` en un carro), que es el caso para el que existe.

## Depende de
004.

## Archivos rectores aplicables
- docs/adr/ADR-007-votacion.md (algoritmo normativo; el paso 5b nuevo ya está añadido en la enmienda del 2026-09-27).
- docs/02-contratos.md §2 (`UnverifiedReason`, ya incluye `CORRECTION_CONFLICT`).
- ARQUITECTURA.md: `domain` solo usa stdlib; la GUI solo traduce la razón a texto.
- reglas-seguridad.md SEG-05 (sin texto de placa en mensajes de error ni logs).

## Archivos a crear/modificar
- `src/lector_placas/domain/entities.py` (miembro nuevo de `UnverifiedReason`)
- `src/lector_placas/domain/consolidation.py` (paso 5b)
- `src/lector_placas/gui/labels.py` (texto de la razón nueva en `REASON_TEXTS`)
- `tests/unit/domain/test_consolidation.py` (un caso modificado y casos nuevos)

## Dependencias externas
Ninguna.

## Interfaces y tipos involucrados
- `UnverifiedReason` gana el miembro `CORRECTION_CONFLICT` con valor `"correction_conflict"`, **al final** del enum
  (después de `AMBIGUOUS_FORMAT`). El orden del enum es el orden canónico de `reasons`; añadirlo al final deja igual el
  orden de todas las combinaciones existentes.
- `VotingPlateConsolidator.consolidate` mantiene su firma. No cambian `ConsolidationPolicy`, `ConsolidatedPlate`,
  `PlateFormatCatalog` ni `correct_to_pattern`.
- En BD, `sightings.reasons` es texto sin `CHECK` de valores y `rows._split_reasons` construye el enum a partir del
  valor, así que no hay migración. Las filas antiguas se siguen leyendo igual.

## Comportamiento esperado
Numeración de ADR-007. Los pasos 1–5 y 6 no cambian; el paso 5b se ejecuta después de elegir la selección (tras el 6)
y antes de sumar las razones de métricas (paso 7).

1. **Voto sin corrección:** sobre las mismas lecturas de longitud `L` (paso 2), se calcula el voto por posición sin
   aplicar ninguna corrección. Es exactamente el cálculo que ya se usa como respaldo cuando no hay patrón (mismo
   texto, confianza y acuerdo; mismo desempate). Se llama *texto directo*.
2. **Formatos del texto directo:** los formatos del catálogo cuya regex acepta el texto directo completo, en orden del
   catálogo (`PlateFormatCatalog.matching`).
3. **Conflicto:** hay conflicto si esa lista no está vacía **y** el texto directo es distinto del texto de la selección
   de los pasos 3–6. Sin conflicto, el resultado es exactamente el de hoy.
4. **Resultado con conflicto:**
   - Texto, confianza y acuerdo: los del texto directo.
   - `format_ids`: los ids de los formatos del texto directo que admiten el tipo de vehículo del track; si ninguno lo
     admite, los ids de todos los formatos del texto directo. En ambos casos, en orden del catálogo.
   - Razones de selección (se descartan las que traía la selección por patrones):
     `CORRECTION_CONFLICT` siempre; `VEHICLE_FORMAT_MISMATCH` si ningún formato del texto directo admite el tipo de
     vehículo; `UNVERIFIED_FORMAT` si alguno lo admite pero ninguno de esos está verificado.
     No se añade `AMBIGUOUS_FORMAT`: el conflicto ya expresa esa duda.
5. Después, las razones de métricas del paso 7 (`INSUFFICIENT_READINGS`, `LOW_CONFIDENCE`, `LOW_AGREEMENT` y la de
   empate de longitud) se suman como hoy, calculadas con la confianza y el acuerdo del resultado final. La lista sale
   sin duplicados y en el orden del enum. Con `CORRECTION_CONFLICT` presente, el estado es siempre `UNVERIFIED`.
6. Si el voto sin corrección no encaja en ningún formato, no hay conflicto posible: la corrección posicional funciona
   como hoy (incluido el caso de `UNRECOGNIZED_FORMAT` cuando ningún patrón da un formato válido).
7. `gui/labels.py`: `REASON_TEXTS[UnverifiedReason.CORRECTION_CONFLICT] = "Podría ser otra placa: una letra o un
   número dudoso"`. La ventana OpenCV de la CLI muestra el valor crudo de la razón y no requiere cambios.

Complejidad: un voto adicional por track, del mismo orden que los que ya se hacen por patrón.

## Casos borde y manejo de errores
- Texto directo válido e igual a la selección (el caso normal: `ABC123` en un carro, `XYZ98K` en una moto): sin
  conflicto, sin cambios.
- Mayoría que coincide con la corrección: tres `XYZ98B` y un `XYZ988` en una moto → el texto directo ya es `XYZ98B`,
  igual a la selección; se confirma como hoy. La corrección solo arregla lecturas minoritarias.
- Mapa de confusiones vacío: la selección nunca corrige, así que no hay conflicto; el comportamiento es el de hoy.
- Ningún mensaje de error ni log nuevo. Si se añadiera alguno, sin texto de placa (SEG-05).

## Tests de aceptación
En `tests/unit/domain/test_consolidation.py`, con los auxiliares que ya tiene el archivo (`rd`, `consolidator`,
catálogo de `tests/fixtures/plate_catalog.py`, `POLICY` con `min_readings=3`, `confirm_threshold=0.90`,
`min_agreement=0.60`, `ambiguity_margin=0.10`) y textos sintéticos.

Caso existente que cambia (la expectativa vieja es justo el defecto que corrige esta spec):

1. `test_vehicle_type_disambiguates_correction`: mismas lecturas (`ABC12S`, `ABC125`, `ABC125`, confianza 0,95).
   - Carro: sin cambios → `ABC125`, `CONFIRMED`, acuerdo 1,0.
   - Moto: ahora `ABC125`, `UNVERIFIED`, razones `(LOW_CONFIDENCE, VEHICLE_FORMAT_MISMATCH, CORRECTION_CONFLICT)`,
     `format_ids == ("co_particular_publico", "co_diplomatico_2015")`. La confianza es la del voto directo
     (1,9/3 en la última posición) y el acuerdo, 2/3.

Casos nuevos:

2. `test_moto_track_keeps_valid_car_reading`: tres `KLM128` (0,99) en `MOTORCYCLE` → texto `KLM128`, `UNVERIFIED`,
   razones `(VEHICLE_FORMAT_MISMATCH, CORRECTION_CONFLICT)`, `format_ids == ("co_particular_publico",)`, confianza
   ≈ 0,99, acuerdo 1,0. Reproduce el defecto real con texto sintético.
3. `test_same_reading_on_car_track_confirms`: tres `KLM128` (0,99) en `CAR` → `CONFIRMED`, razones vacías,
   `format_ids == ("co_particular_publico",)`.
4. `test_majority_letter_still_corrected_and_confirmed`: tres `XYZ98B` y un `XYZ988` (0,97) en `MOTORCYCLE` → texto
   `XYZ98B`, `CONFIRMED`, `format_ids == ("co_moto",)`, acuerdo 1,0.
5. `test_invalid_direct_reading_is_still_corrected`: tres `0BC123` (0,99) en `CAR` → texto `OBC123`, `CONFIRMED`,
   `format_ids == ("co_particular_publico", "co_diplomatico_2015")`. La corrección sigue funcionando cuando el voto
   directo no es una placa.
6. `test_correction_conflict_is_last_in_canonical_order`: `UnverifiedReason` termina en `CORRECTION_CONFLICT`, con
   valor `"correction_conflict"`, y los siete miembros anteriores conservan nombre, valor y orden.

Los demás casos de `test_consolidation.py`, `tests/review/test_review_004.py` y
`tests/unit/gui/test_labels.py` (que exige un texto no vacío para cada razón) pasan sin modificarse.

## Fuera de alcance
- Cambiar umbrales, el mapa de confusiones o el catálogo de formatos.
- Penalizar la confianza de las posiciones corregidas cuando no hay conflicto (docs/07, alternativa descartada por
  ahora).
- Mejorar la clasificación del tipo de vehículo.
- Reconsolidar avistamientos ya guardados: la BD no conserva las lecturas individuales.

## Definition of Done
- `uv run pytest tests/unit/domain tests/unit/gui tests/review tests/architecture` pasa.
- `uv run pytest` completo pasa (los tests de GUI con `QT_QPA_PLATFORM=offscreen`).
- `uv run ruff check . && uv run ruff format --check .` y `uv run mypy src` sin errores.
- Solo cambian los cuatro archivos listados.
