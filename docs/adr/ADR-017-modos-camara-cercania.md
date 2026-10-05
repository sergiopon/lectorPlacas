# ADR-017 — Modos de cámara y filtro de cercanía

- Estado: **Aprobado** (2026-10-03): el usuario aprobó el umbral de cercanía, que el modo móvil trabaje solo sobre
  archivos de video y la renumeración de las specs. Diseño completo y cifras en `docs/historial/09-enfoque-versatil.md`.
- Requisitos afectados: RF-03, RF-04, RF-08, RF-34, nuevo RF-37; SEG-03, SEG-20, nueva SEG-29.
- El ADR-016 queda reservado para la interfaz web (docs/historial/08 §4.1).

## Contexto
El usuario decidió (2026-10-03) que solo interesan las placas **legibles y cercanas** y que el sistema debe servir en dos
modos: **cámara estática** (parqueaderos, entradas, calles) y **cámara móvil en vehículo** (patrullas y similares). Datos
medidos (docs/historial/09 §1.1): de 1 113 avistamientos revisados, 329 legibles, 422 borrosos y 362 no-placa; el ancho del mejor
recorte de las legibles tiene mediana 59 px; el 17 % de las legibles son duplicados dentro de su corrida.

## Decisión
1. **Cercanía = ancho de la caja de la placa en el frame.** Mínimo efectivo
   `ceil(max(min_plate_width_px, near_min_width_frac × lado mayor del frame))`, con 32 px y 0,025 por defecto (48 px en
   1080p, 32 px en 720p). Lo que no llega al mínimo no se lee, no se guarda y no se revisa (spec 057).
2. **El modo es un campo del perfil** (`mode`: `estatico` o `movil`), no una bifurcación del pipeline. Un solo código; el
   modo obliga valores mediante la validación (el móvil exige compensación de movimiento de cámara) y separa resultados
   (spec 056). Perfil nuevo `patrulla` (`movil`).
3. **La compensación de movimiento de cámara (CMC) es un campo por perfil.** Enmienda de ADR-004: ya no está "siempre
   activo". Los cuatro perfiles la dejan encendida hasta que el experimento E3 (docs/historial/09 §6) demuestre que apagarla en
   estático no fragmenta tracks.
4. **Duplicados de la misma placa en una corrida: se marcan, no se borran** (`duplicate_of`, ventana de 30 000 ms,
   specs 059 y 061).
5. **Fuente de video: solo archivos.** Sin cámara en vivo (velocidad medida 0,85× del tiempo real; una cámara IP exigiría
   abrir una excepción a SEG-20), sin GPS y sin hora absoluta de grabación.
6. **Privacidad del modo móvil: SEG-29.** Sin ubicación, sin cotejo con listas de placas buscadas ni alertas, y solo se
   guarda el recorte de la placa.

## Alternativas descartadas
| Alternativa | Motivo |
|---|---|
| Bifurcar el pipeline por modo | Duplica código y pruebas; todo lo que difiere cabe en campos del perfil. |
| Medir la cercanía por la altura del vehículo | La placa es lo que decide si el OCR lee; el vehículo solo sirve como prefiltro barato (`max_plate_vehicle_ratio`). |
| ROI poligonal | Exige elegir y probar un algoritmo de punto en polígono sin un caso medido que lo pida; la ROI es un rectángulo. |
| Borrar los duplicados | Puede esconder una placa distinta; marcarlos es reversible. |
| Fuente en vivo (RTSP, V4L2) | Fuera de alcance: rendimiento por debajo de 1×, excepción a SEG-20 y otro diseño de descarte. Se reabre con M-05 ≥ 1,2× y un ADR propio. |
| Guardar ubicación o hora absoluta | Convierte la lectura en un historial de movimientos de personas (SEG-29). |

## Consecuencias
- (+) Un solo pipeline; la revisión deja de ver lo lejano; el modo móvil se calibra por configuración.
- (−) Hasta el 34 % de las legibles actuales tiene el mejor recorte por debajo de 50 px (cota pesimista): se pierden
  placas legibles más lejanas, aceptado por el usuario.
- (−) El modo móvil queda **no validado** hasta tener material grabado desde un vehículo (experimento E6).
- (−) La base legal de un uso policial o por una entidad está **PENDIENTE DE VALIDAR** (Ley 1581 de 2012 art. 2, Ley 1843
  de 2017 u otras); el README no debe presentar el modo móvil como apto para ese uso.
