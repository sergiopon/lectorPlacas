# ADR-010 — Decodificación de video con PyAV

- Estado: Aceptado (2026-09-24)
- Requisitos: RF-01, RF-23 (timestamp relativo en ms)

## Contexto
Videos de celular: fps variable, rotación en metadatos (display matrix), códecs diversos.

## Opciones evaluadas
1. OpenCV `VideoCapture`: timestamps derivados del índice/fps (incorrectos con VFR).
2. **PyAV 18.1.0** (BSD-3, FFmpeg 8.x incluido, wheels abi3): `frame.pts`, `frame.time_base`,
   `frame.time` (segundos), `frame.rotation` (grados antihorarios en [-180, 180] leídos de
   `AV_FRAME_DATA_DISPLAYMATRIX`, verificado en el código fuente v18.1.0), `frame.to_ndarray(format="bgr24")`.

## Decisión
PyAV para decodificar. `timestamp_ms = round((frame.pts - primer_pts) * frame.time_base * 1000)`
(relativo al primer frame decodificado). Rotación: `np.rot90(imagen, k=(round(rotation / 90)) % 4)`
(np.rot90 rota en sentido antihorario, igual que la convención de `frame.rotation`).
Frames sin `pts` se descartan con log `WARNING`. OpenCV solo para procesamiento de imagen.

## Consecuencias
- (+) Timestamps correctos con VFR; videos verticales se procesan derechos.
- (−) El test de aceptación con video sintético rotado (spec 010) es la verificación de que FFmpeg
  propaga la display matrix al frame; si falla, se detiene la implementación y se revisa este ADR.
