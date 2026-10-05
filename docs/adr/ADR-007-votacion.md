# ADR-007 — Votación y consolidación por track

- Estado: Aceptado (2026-09-24)
- Requisitos: RF-10..RF-17; M-01 (precisión confirmadas ≥ 98 %)

## Contexto
Cada track acumula varias lecturas OCR con probabilidad por carácter. Hay que producir un texto,
aplicar corrección posicional (0↔O, 1↔I, 8↔B, 5↔S), validar contra el catálogo de formatos y el tipo
de vehículo, y decidir `confirmed` vs `unverified` con prioridad a la precisión. Formatos de igual
longitud (p. ej. `LLLDDD` carro y `LLLDDL` moto) hacen que la corrección sea ambigua sin contexto.

## Opciones evaluadas
1. Voto por texto completo (mayoría de cadenas): desperdicia lecturas parcialmente correctas.
2. Voto por carácter sin formato: no aprovecha la estructura de la placa.
3. **Voto por carácter ponderado por probabilidad, por patrón candidato**, con corrección
   posicional previa al voto y desempate por tipo de vehículo.

## Decisión (algoritmo normativo)
1. Longitud objetivo `L` = longitud con mayor suma de `mean_confidence` entre las lecturas; empate
   exacto → la mayor longitud, y se añade la razón `LOW_AGREEMENT`.
2. Lecturas usadas = las de longitud `L` (`n = len`).
3. Patrones candidatos = patrones distintos del catálogo con longitud `L`. Si no hay ninguno:
   voto sin corrección y razón `UNRECOGNIZED_FORMAT`.
4. Por cada patrón `P`: corregir cada lectura a `P`; votar por posición sumando la probabilidad del
   carácter; ganador por posición = mayor suma (empate → orden alfabético/ASCII menor).
   `score_pos = suma_ganador / n`; `confianza_P = min(score_pos)`;
   `acuerdo_P = lecturas_corregidas_idénticas_al_texto / n`.
   Se conserva `P` si algún formato de patrón `P` cumple su regex con el texto ganador.
5. Compatibles = resultados con algún formato coincidente que incluya el tipo de vehículo del track.
   Ninguno compatible pero hay conservados → mejor por confianza, razón `VEHICLE_FORMAT_MISMATCH`.
   Ninguno conservado → voto sin corrección, razón `UNRECOGNIZED_FORMAT`.
5b. (Enmienda 2026-09-27.) Voto directo = voto por posición **sin** corrección sobre las
   mismas `n` lecturas. Si su texto cumple la regex de algún formato del catálogo y es distinto del
   texto elegido en los pasos 5–6, el resultado pasa a ser el voto directo (texto, confianza y
   acuerdo), con `format_ids` de sus formatos compatibles con el vehículo (o de todos si no hay
   compatibles) y razones `CORRECTION_CONFLICT`, más `VEHICLE_FORMAT_MISMATCH` si ninguno es
   compatible o `UNVERIFIED_FORMAT` si ninguno compatible está verificado. Se evalúa tras el paso 6.
6. Varios compatibles → el de mayor confianza; si el segundo está a menos de `ambiguity_margin`
   (0.10) → razón `AMBIGUOUS_FORMAT`.
7. `CONFIRMED` solo si no hay razones y además: `n ≥ min_readings`, `confianza ≥ confirm_threshold`,
   `acuerdo ≥ min_agreement` y algún formato coincidente compatible con `verified = true`.
   En caso contrario `UNVERIFIED` con todas las razones que apliquen
   (`INSUFFICIENT_READINGS`, `LOW_CONFIDENCE`, `LOW_AGREEMENT`, `UNVERIFIED_FORMAT`, …).

## Consecuencias
- (+) Determinista, explicable (razones guardadas en BD), testeable con lecturas sintéticas.
- (+) Los formatos no verificados nunca se confirman (RF-15).
- (−) Parámetros provisionales hasta la calibración de Fase 5.
- (−, corregido por 5b) Sin el paso 5b, un track mal clasificado como moto con lecturas unánimes
  `LLLDDD` se "corregía" a `LLLDDL` y se confirmaba con la confianza del dígito original: 2 de 13
  confirmadas auditadas el 2026-09-27 eran erróneas por esta causa.
