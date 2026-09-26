# ADR-013 — Detección de placa dentro del recorte del vehículo

- Estado: Aceptado (2026-09-24)
- Requisitos: RF-07, RF-10, RNF-01

## Contexto
Hay que asociar cada placa a un track de vehículo. Detectar placas en el frame completo exige una
heurística de asociación (contención/IoU) y reduce la resolución efectiva de placas pequeñas.

## Opciones evaluadas
1. Detector de placas en frame completo + asociación geométrica.
2. **Detector de placas sobre el recorte del vehículo** (con margen del 10 %), solo en tracks que
   aún necesitan lecturas.
3. Un solo modelo con clases vehículo+placa: requiere re-etiquetar vehículos en los datasets de placas.

## Decisión
Opción 2. El recorte se expande `vehicle_crop_margin` por lado, se recorta a los límites del frame y
se pasa al `PlateDetector`. Se toma la detección de mayor confianza; su caja se traslada a
coordenadas del frame. Si el recorte expandido tiene ancho o alto < 16 px se omite.

## Consecuencias
- (+) Asociación placa↔track trivial y sin errores de asignación.
- (+) Costo proporcional al número de tracks pendientes, no al área del frame.
- (−) Si el detector de vehículos falla, la placa no se lee (aceptado: precisión primero).
- (−) Si un recorte contiene placas de dos vehículos (oclusión), se elige la de mayor confianza.
